"""NVA discovery against the real ``azure-mgmt-compute`` SDK, offline.

``TestCollectNvas`` in ``test_azure_discovery.py`` replaces the whole SDK with a mock, so a
release of ``azure-mgmt-compute`` that renames or drops something this repository reads would
pass CI and only fail against a customer's subscription. Dependabot moved the package from
38.4.0 to 39.0.0 while no test touched a single real SDK class. The tests here close that gap
for the one place the repository uses the package, ``AzureDiscovery._collect_nvas``:

* the real ``ComputeManagementClient`` is built, with a fake credential and an HTTP transport
  whose lowest layer (a ``requests`` adapter) answers from JSON, so azure-core's pipeline, the
  SDK's request building, paging and model deserialisation all run for real;
* the real ``_collect_nvas`` runs on top of it and must still find every VM field it reads
  (plan, image reference, OS disk, hardware profile, network profile, tags);
* sockets are blocked, so nothing can leave the machine. No credentials, no sleeps.

The JSON follows the wire shape of the Azure REST API reference for ``Virtual Machines - List
All`` (properties nested under ``properties``, ``plan`` beside them, ``nextLink`` paging). It
is written by hand, not captured from a live subscription, and holds placeholder identifiers.

The module is skipped, with its reason, when the SDK is not installed (the ``enrichment`` and
``api`` extras install it; CI installs both).
"""

from __future__ import annotations

import io
import json
import logging
import socket
from types import SimpleNamespace
from unittest.mock import MagicMock
from urllib.parse import parse_qs, urlsplit

import pytest
import requests.adapters
from azure.core.credentials import AccessToken
from azure.core.pipeline.transport import RequestsTransport
from urllib3.response import HTTPResponse

compute = pytest.importorskip(
    "azure.mgmt.compute", reason="needs azure-mgmt-compute (the [enrichment] or [api] extra)"
)

from network_assessment.modules.network.discovery.azure_discovery import (  # noqa: E402
    AzureDiscovery,
    AzureDiscoveryOptions,
)

SUBSCRIPTION = "11111111-1111-1111-1111-111111111111"  # a placeholder, not a real subscription
ARM_HOST = "management.azure.com"
LIST_PATH = f"/subscriptions/{SUBSCRIPTION}/providers/Microsoft.Compute/virtualMachines"
ARM_SCOPE = "https://management.azure.com/.default"
FAKE_TOKEN = "not-a-real-token"
FAR_FUTURE = 4_102_444_800  # 2100-01-01: the bearer policy never asks for a second token


# --------------------------------------------------------------------------- wire-shape JSON


def _vm_id(group: str, name: str) -> str:
    return (
        f"/subscriptions/{SUBSCRIPTION}/resourceGroups/{group}"
        f"/providers/Microsoft.Compute/virtualMachines/{name}"
    )


def _nic_id(group: str, name: str) -> str:
    return (
        f"/subscriptions/{SUBSCRIPTION}/resourceGroups/{group}"
        f"/providers/Microsoft.Network/networkInterfaces/{name}"
    )


def _vm_json(name, *, image, nic_names, plan=None, tags=None, group="rg-hub"):
    """One element of ``value`` in a ``Virtual Machines - List All`` response."""
    vm = {
        "id": _vm_id(group, name),
        "name": name,
        "type": "Microsoft.Compute/virtualMachines",
        "location": "eastus",
        "tags": tags or {},
        "properties": {
            "vmId": "00000000-0000-0000-0000-0000000000a1",
            "hardwareProfile": {"vmSize": "Standard_D4s_v5"},
            "storageProfile": {
                "imageReference": image,
                "osDisk": {
                    "osType": "Linux",
                    "name": f"{name}-osdisk",
                    "createOption": "FromImage",
                    "caching": "ReadWrite",
                    "managedDisk": {"storageAccountType": "Premium_LRS"},
                    "diskSizeGB": 64,
                },
                "dataDisks": [],
            },
            "networkProfile": {
                "networkInterfaces": [
                    {"id": _nic_id("rg-hub-net", nic), "properties": {"primary": index == 0}}
                    for index, nic in enumerate(nic_names)
                ]
            },
            "provisioningState": "Succeeded",
        },
    }
    if plan:
        vm["plan"] = plan
    return vm


# A marketplace firewall: carries both the marketplace plan and the image reference.
FIREWALL = _vm_json(
    "vm-fw-01",
    plan={
        "name": "fortinet_fw-vm",
        "publisher": "fortinet",
        "product": "fortinet_fortigate-vm_v5",
    },
    image={
        "publisher": "fortinet",
        "offer": "fortinet_fortigate-vm_v5",
        "sku": "fortinet_fw-vm",
        "version": "7.4.4",
        "exactVersion": "7.4.4",
    },
    nic_names=["nic-fw-01-untrust", "nic-fw-01-trust"],
    tags={"role": "firewall", "env": "hub"},
)
# An appliance from a vendor image with no plan on the VM (bring your own licence).
BYOL_APPLIANCE = _vm_json(
    "vm-pa-01",
    image={
        "publisher": "paloaltonetworks",
        "offer": "vmseries-flex",
        "sku": "byol",
        "version": "latest",
    },
    nic_names=["nic-pa-01-mgmt"],
)
# A custom router: no recognisable publisher, found only because its NIC forwards IP traffic.
ROUTER = _vm_json(
    "vm-router-01",
    image={
        "publisher": "Canonical",
        "offer": "ubuntu-24_04-lts",
        "sku": "server",
        "version": "latest",
    },
    nic_names=["nic-router-01"],
)
# An ordinary workload: must not be reported.
WEB_SERVER = _vm_json(
    "vm-web-01",
    image={
        "publisher": "Canonical",
        "offer": "ubuntu-24_04-lts",
        "sku": "server",
        "version": "latest",
    },
    nic_names=["nic-web-01"],
)

SECOND_PAGE_TOKEN = "page-2"
PAGES = {
    # ARM answers with a nextLink while there is more; the SDK must follow it.
    None: {"value": [FIREWALL, WEB_SERVER]},
    SECOND_PAGE_TOKEN: {"value": [BYOL_APPLIANCE, ROUTER]},
}
EXPECTED_NVAS = ["vm-fw-01", "vm-pa-01", "vm-router-01"]


# --------------------------------------------------------------------------- the stubs


class _FakeCredential:
    """The part of ``TokenCredential`` the SDK uses; hands out a token that is not one."""

    def __init__(self) -> None:
        self.scopes: list[tuple[str, ...]] = []

    def get_token(self, *scopes, **kwargs):
        self.scopes.append(scopes)
        return AccessToken(FAKE_TOKEN, FAR_FUTURE)


class _StubArm(requests.adapters.HTTPAdapter):
    """Plays Azure Resource Manager at the lowest layer: no socket is ever opened.

    Answers the subscription-wide VM list from ``pages`` and every other request with a 404,
    and remembers what it was asked. ``HTTPAdapter`` supplies ``build_response``; ``send`` is
    replaced entirely.
    """

    def __init__(self, pages) -> None:
        super().__init__()
        self.pages = pages
        self.requests: list[requests.PreparedRequest] = []

    def send(self, request, **kwargs):
        self.requests.append(request)
        url = urlsplit(request.url)
        token = parse_qs(url.query).get("$skiptoken", [None])[0]
        known = (
            request.method == "GET"
            and url.netloc == ARM_HOST
            and url.path.lower() == LIST_PATH.lower()
            and token in self.pages
        )
        if not known:
            return self._respond(
                request, 404, {"error": {"code": "NotStubbed", "message": request.url}}
            )
        body = dict(self.pages[token])
        if token is None:
            body["nextLink"] = (
                f"https://{ARM_HOST}{LIST_PATH}?api-version=x&$skiptoken={SECOND_PAGE_TOKEN}"
            )
        return self._respond(request, 200, body)

    def _respond(self, request, status, body):
        raw = HTTPResponse(
            body=io.BytesIO(json.dumps(body).encode()),
            status=status,
            reason="OK" if status == 200 else "Not Found",
            headers={"Content-Type": "application/json; charset=utf-8"},
            preload_content=False,
        )
        return self.build_response(request, raw)


class _FakeNetworkClient:
    """The slice of ``NetworkManagementClient`` that ``_collect_vm_nics`` reads.

    azure-mgmt-network is not what these tests guard, so its NICs are plain objects. Only
    the NICs named in ``forwarding`` have IP forwarding on.
    """

    def __init__(self, forwarding: set[str]) -> None:
        self.forwarding = forwarding
        self.calls: list[tuple[str, str]] = []
        self.network_interfaces = SimpleNamespace(get=self._get)

    def _get(self, resource_group, name):
        self.calls.append((resource_group, name))
        return SimpleNamespace(
            id=_nic_id(resource_group, name),
            name=name,
            location="eastus",
            enable_ip_forwarding=name in self.forwarding,
            network_security_group=SimpleNamespace(id=f"nsg-of-{name}"),
            ip_configurations=[
                SimpleNamespace(
                    subnet=SimpleNamespace(id=f"subnet-of-{name}"),
                    private_ip_address="10.0.1.4",
                    public_ip_address=None,
                )
            ],
        )


# --------------------------------------------------------------------------- the run


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Fail loudly if anything tries to leave the machine instead of reaching the stub."""

    def refuse(*args, **kwargs):
        raise AssertionError("this test must stay offline: something opened a connection")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)


@pytest.fixture
def run(monkeypatch, caplog):
    """Run the real ``_collect_nvas`` once over the real SDK and the stubs."""
    caplog.set_level(
        logging.DEBUG, logger="network_assessment.discovery.azure"
    )  # shows what _safe_list swallows
    credential = _FakeCredential()
    arm = _StubArm(PAGES)
    session = requests.Session()
    session.mount("https://", arm)
    session.mount("http://", arm)
    transport = RequestsTransport(session=session)

    real_client = compute.ComputeManagementClient
    built: list = []

    def build_client(cred, subscription_id):
        # The only seam: the repository builds the client itself, so the stub transport is
        # handed to the *real* class. The credential and subscription pass through untouched.
        client = real_client(cred, subscription_id, transport=transport)
        built.append(client)
        return client

    monkeypatch.setattr(compute, "ComputeManagementClient", build_client)

    discovery = AzureDiscovery(
        store=MagicMock(),
        options=AzureDiscoveryOptions(
            tenant_id="00000000-0000-0000-0000-000000000001",
            subscription_ids=[SUBSCRIPTION],
            backend="arm",
        ),
    )
    discovery._credential = credential
    net = _FakeNetworkClient(forwarding={"nic-fw-01-untrust", "nic-fw-01-trust", "nic-router-01"})

    nvas = discovery._collect_nvas(net, SUBSCRIPTION)
    return SimpleNamespace(
        nvas=nvas, arm=arm, credential=credential, net=net, clients=built, log=caplog.text
    )


def _os_family(os_type: str | None) -> str:
    """``linux`` for ``Linux`` and for ``OperatingSystemTypes.LINUX``.

    ``_collect_nvas`` turns the SDK's ``OperatingSystemTypes`` enum into text with ``str()``,
    which spells it ``OperatingSystemTypes.LINUX`` (the Resource Graph backend stores
    ``Linux``). This guard only needs the OS type to arrive, so it accepts either spelling and
    does not pin the current one.
    """
    return (os_type or "").rsplit(".", 1)[-1].lower()


# --------------------------------------------------------------------------- the tests


def test_the_client_that_ran_is_the_real_sdk(run):
    """Not a mock: the real class, its real operations group, and the stub really answered."""
    assert len(run.clients) == 1
    client = run.clients[0]
    assert type(client).__module__.startswith("azure.mgmt.compute")
    assert type(client.virtual_machines).__module__.startswith("azure.mgmt.compute.operations")
    assert run.arm.requests, "the real SDK never reached the stubbed transport: " + run.log


def test_the_sdk_asks_for_every_vm_in_the_subscription_page_by_page(run):
    first, second = run.arm.requests  # one request per page, nothing else
    for request in (first, second):
        assert request.method == "GET"
        url = urlsplit(request.url)
        assert url.netloc == ARM_HOST
        assert url.path.lower() == LIST_PATH.lower()
        assert parse_qs(url.query).get("api-version", [""])[0]
        assert request.headers["Authorization"] == f"Bearer {FAKE_TOKEN}"
    assert "$skiptoken" not in first.url
    assert f"$skiptoken={SECOND_PAGE_TOKEN}" in second.url
    assert run.credential.scopes
    assert set(run.credential.scopes) == {(ARM_SCOPE,)}


def test_only_the_network_virtual_appliances_are_found_across_both_pages(run):
    assert [nva.name for nva in run.nvas] == EXPECTED_NVAS, run.log


def test_a_marketplace_plan_is_read_into_every_field_the_repository_keeps(run):
    firewall = run.nvas[0]
    assert firewall.id == _vm_id("rg-hub", "vm-fw-01")
    assert firewall.name == "vm-fw-01"
    assert firewall.location == "eastus"
    assert firewall.resource_group == "rg-hub"
    assert firewall.vm_size == "Standard_D4s_v5"
    assert _os_family(firewall.os_type) == "linux"
    assert firewall.identification_method == "marketplace"
    assert firewall.publisher == "fortinet"
    assert firewall.offer == "fortinet_fortigate-vm_v5"
    assert firewall.plan_name == "fortinet_fw-vm"
    assert firewall.tags == {"role": "firewall", "env": "hub"}


def test_the_network_profile_leads_to_the_nics_of_each_vm(run):
    firewall = run.nvas[0]
    # Every VM's NICs are read, including the one that is not reported (vm-web-01).
    assert run.net.calls == [
        ("rg-hub-net", "nic-fw-01-untrust"),
        ("rg-hub-net", "nic-fw-01-trust"),
        ("rg-hub-net", "nic-web-01"),
        ("rg-hub-net", "nic-pa-01-mgmt"),
        ("rg-hub-net", "nic-router-01"),
    ]
    assert [nic.name for nic in firewall.nics] == ["nic-fw-01-untrust", "nic-fw-01-trust"]
    first_nic = firewall.nics[0]
    assert first_nic.id == _nic_id("rg-hub-net", "nic-fw-01-untrust")
    assert first_nic.resource_group == "rg-hub-net"
    assert first_nic.vm_id == firewall.id
    assert first_nic.ip_forwarding_enabled is True
    assert first_nic.tags == {"role": "firewall", "env": "hub"}


def test_an_image_reference_alone_identifies_a_vendor_appliance(run):
    appliance = next(nva for nva in run.nvas if nva.name == "vm-pa-01")
    assert appliance.identification_method == "image_reference"
    assert appliance.publisher == "paloaltonetworks"
    assert appliance.offer == "vmseries-flex"
    assert appliance.plan_name == "byol"
    assert appliance.vm_size == "Standard_D4s_v5"
    assert _os_family(appliance.os_type) == "linux"


def test_a_vm_with_no_plan_and_no_known_vendor_is_found_by_ip_forwarding(run):
    router = next(nva for nva in run.nvas if nva.name == "vm-router-01")
    assert router.identification_method == "ip_forwarding"
    assert (router.publisher, router.offer, router.plan_name) == (None, None, None)
    assert [nic.name for nic in router.nics] == ["nic-router-01"]
