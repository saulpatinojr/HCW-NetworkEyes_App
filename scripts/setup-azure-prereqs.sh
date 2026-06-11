#!/usr/bin/env bash
# =============================================================================
# setup-azure-prereqs.sh
# =============================================================================
# One-time (idempotent) setup script for GitHub Actions → Azure OIDC.
#
# What it does:
#   1. Creates (or finds existing) Entra ID app registration
#   2. Creates the service principal for that app
#   3. Assigns Contributor + User Access Administrator on the subscription
#   4. Adds a federated credential for the target GitHub branch
#   5. Sets all required GitHub Secrets via gh CLI
#   6. Sets all required GitHub Variables via gh CLI
#
# Prerequisites:
#   - az CLI: https://learn.microsoft.com/en-us/cli/azure/install-azure-cli
#   - gh CLI: https://cli.github.com/
#   - az login  (run before this script)
#   - gh auth login  (run before this script)
#
# Usage:
#   chmod +x scripts/setup-azure-prereqs.sh
#   ./scripts/setup-azure-prereqs.sh
#
# Safe to re-run: all steps check for existing resources before creating.
# =============================================================================

set -euo pipefail

# ── Configuration ─────────────────────────────────────────────────────────────
# Edit these values before running.

APP_DISPLAY_NAME="cna-platform"
GITHUB_ORG="saulpatinojr"
GITHUB_REPO="MVP-Cloud_Network_Assessment"
BRANCH="main"

# Roles granted to the service principal on the subscription.
# Contributor  → Terraform can create/modify/delete all resources
# User Access Administrator → Terraform can assign roles to managed identities
ROLES=("Contributor" "User Access Administrator")

# GitHub Variables to set (non-sensitive, visible in logs)
# Update any placeholder values before running.
declare -A GH_VARIABLES=(
  [TFSTATE_RESOURCE_GROUP]="rg-cna-tfstate"
  [TFSTATE_STORAGE_ACCOUNT]="stcnatfstate"
  [TFSTATE_CONTAINER]="tfstate"
  [CNA_ENTRA_CLIENT_ID]="PLACEHOLDER_UPDATE_AFTER_APP_REGISTRATION"
  [CNA_NEXTAUTH_URL]="https://cna.example.com"
  [CNA_AZURE_OPENAI_DEPLOYMENT]="gpt-4o"
  [APPLICATION_INSIGHTS_NAME]="none"
  [KEY_VAULT_NAME]="none"
)

# ── Colors ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

info()    { echo -e "${BLUE}[INFO]${NC} $*"; }
success() { echo -e "${GREEN}[OK]${NC}   $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $*"; }
error()   { echo -e "${RED}[ERR]${NC}  $*"; }
header()  { echo -e "\n${BOLD}==> $*${NC}"; }

# ── Preflight checks ──────────────────────────────────────────────────────────
header "Checking prerequisites"

if ! command -v az &>/dev/null; then
  error "az CLI not found. Install: https://learn.microsoft.com/en-us/cli/azure/install-azure-cli"
  exit 1
fi
success "az CLI found"

if ! command -v gh &>/dev/null; then
  error "gh CLI not found. Install: https://cli.github.com/"
  exit 1
fi
success "gh CLI found"

if ! az account show &>/dev/null; then
  error "Not logged in to Azure. Run: az login"
  exit 1
fi
success "Azure login active"

if ! gh auth status &>/dev/null; then
  error "Not logged in to GitHub. Run: gh auth login"
  exit 1
fi
success "GitHub login active"

# ── Gather subscription + tenant ─────────────────────────────────────────────
header "Gathering Azure account info"

SUBSCRIPTION_ID=$(az account show --query id -o tsv)
TENANT_ID=$(az account show --query tenantId -o tsv)
SUBSCRIPTION_NAME=$(az account show --query name -o tsv)

info "Subscription : $SUBSCRIPTION_NAME ($SUBSCRIPTION_ID)"
info "Tenant       : $TENANT_ID"
info "GitHub repo  : $GITHUB_ORG/$GITHUB_REPO (branch: $BRANCH)"

# ── App registration ──────────────────────────────────────────────────────────
header "App registration: $APP_DISPLAY_NAME"

EXISTING_APP=$(az ad app list --display-name "$APP_DISPLAY_NAME" --query "[0].appId" -o tsv 2>/dev/null || echo "")

if [[ -n "$EXISTING_APP" && "$EXISTING_APP" != "None" ]]; then
  APP_ID="$EXISTING_APP"
  success "Already exists — App ID: $APP_ID"
else
  info "Creating app registration..."
  APP_ID=$(az ad app create \
    --display-name "$APP_DISPLAY_NAME" \
    --query appId -o tsv)
  success "Created — App ID: $APP_ID"
fi

# ── Service principal ─────────────────────────────────────────────────────────
header "Service principal"

EXISTING_SP=$(az ad sp list --filter "appId eq '$APP_ID'" --query "[0].id" -o tsv 2>/dev/null || echo "")

if [[ -n "$EXISTING_SP" && "$EXISTING_SP" != "None" ]]; then
  success "Already exists"
else
  info "Creating service principal..."
  az ad sp create --id "$APP_ID" --output none
  # RBAC propagation can take a few seconds
  sleep 15
  success "Created"
fi

# ── Role assignments ──────────────────────────────────────────────────────────
header "Role assignments (subscription scope)"

SCOPE="/subscriptions/$SUBSCRIPTION_ID"

for ROLE in "${ROLES[@]}"; do
  EXISTING_ROLE=$(az role assignment list \
    --assignee "$APP_ID" \
    --role "$ROLE" \
    --scope "$SCOPE" \
    --query "[0].id" -o tsv 2>/dev/null || echo "")

  if [[ -n "$EXISTING_ROLE" && "$EXISTING_ROLE" != "None" ]]; then
    success "Already assigned: $ROLE"
  else
    info "Assigning: $ROLE..."
    az role assignment create \
      --role "$ROLE" \
      --assignee "$APP_ID" \
      --scope "$SCOPE" \
      --output none
    success "Assigned: $ROLE"
  fi
done

# ── Federated credential ──────────────────────────────────────────────────────
header "Federated credential (branch: $BRANCH)"

CREDENTIAL_NAME="${GITHUB_REPO}-github-${BRANCH}"
SUBJECT="repo:${GITHUB_ORG}/${GITHUB_REPO}:ref:refs/heads/${BRANCH}"

EXISTING_CRED=$(az ad app federated-credential list \
  --id "$APP_ID" \
  --query "[?name=='$CREDENTIAL_NAME'].id" -o tsv 2>/dev/null || echo "")

if [[ -n "$EXISTING_CRED" ]]; then
  success "Already exists: $CREDENTIAL_NAME"
else
  info "Creating federated credential..."
  az ad app federated-credential create \
    --id "$APP_ID" \
    --parameters "{
      \"name\": \"$CREDENTIAL_NAME\",
      \"issuer\": \"https://token.actions.githubusercontent.com\",
      \"subject\": \"$SUBJECT\",
      \"audiences\": [\"api://AzureADTokenExchange\"]
    }" --output none
  success "Created: $CREDENTIAL_NAME"
  info "Subject: $SUBJECT"
fi

# ── GitHub Secrets ────────────────────────────────────────────────────────────
header "GitHub Secrets → $GITHUB_ORG/$GITHUB_REPO"

set_secret() {
  local name="$1"
  local value="$2"
  info "Setting secret: $name"
  echo "$value" | gh secret set "$name" \
    --repo "$GITHUB_ORG/$GITHUB_REPO" \
    --body -
  success "Set: $name"
}

set_secret "AZURE_CLIENT_ID"       "$APP_ID"
set_secret "AZURE_TENANT_ID"       "$TENANT_ID"
set_secret "AZURE_SUBSCRIPTION_ID" "$SUBSCRIPTION_ID"

warn "The following secrets must be set manually (sensitive values this script cannot generate):"
warn "  GHCR_PAT                — GitHub classic PAT with read:packages scope"
warn "  CNA_POSTGRES_ADMIN_PASSWORD — generate: openssl rand -base64 16"
warn "  CNA_ENTRA_CLIENT_SECRET     — OAuth client secret from your Entra app"
warn "  CNA_NEXTAUTH_SECRET         — generate: openssl rand -base64 32"

# ── GitHub Variables ──────────────────────────────────────────────────────────
header "GitHub Variables → $GITHUB_ORG/$GITHUB_REPO"

# Update CNA_ENTRA_CLIENT_ID with the real app ID now that we have it
GH_VARIABLES[CNA_ENTRA_CLIENT_ID]="$APP_ID"

for VAR_NAME in "${!GH_VARIABLES[@]}"; do
  VAR_VALUE="${GH_VARIABLES[$VAR_NAME]}"
  info "Setting variable: $VAR_NAME = $VAR_VALUE"
  gh variable set "$VAR_NAME" \
    --repo "$GITHUB_ORG/$GITHUB_REPO" \
    --body "$VAR_VALUE"
  success "Set: $VAR_NAME"
done

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}══════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}${BOLD}  Setup Complete${NC}"
echo -e "${BOLD}══════════════════════════════════════════════════════${NC}"
echo ""
echo -e "  ${BOLD}Azure${NC}"
echo -e "  App Registration : $APP_DISPLAY_NAME"
echo -e "  App (Client) ID  : $APP_ID"
echo -e "  Tenant ID        : $TENANT_ID"
echo -e "  Subscription     : $SUBSCRIPTION_NAME"
echo -e "  Roles assigned   : ${ROLES[*]}"
echo -e "  Federated cred   : $CREDENTIAL_NAME"
echo ""
echo -e "  ${BOLD}GitHub Secrets set automatically${NC}"
echo -e "  AZURE_CLIENT_ID, AZURE_TENANT_ID, AZURE_SUBSCRIPTION_ID"
echo ""
echo -e "  ${BOLD}GitHub Variables set automatically${NC}"
for VAR_NAME in "${!GH_VARIABLES[@]}"; do
  echo -e "  $VAR_NAME = ${GH_VARIABLES[$VAR_NAME]}"
done
echo ""
echo -e "  ${YELLOW}${BOLD}Manual secrets still required:${NC}"
echo -e "  ${YELLOW}  GHCR_PAT, CNA_POSTGRES_ADMIN_PASSWORD,${NC}"
echo -e "  ${YELLOW}  CNA_ENTRA_CLIENT_SECRET, CNA_NEXTAUTH_SECRET${NC}"
echo ""
echo -e "  ${BOLD}Next step:${NC} Run workflow 01 (Bootstrap Terraform Backend)"
echo -e "  ${BOLD}Then:${NC}      Run workflow 00 (Validate Prerequisites) to confirm all is green"
echo ""
