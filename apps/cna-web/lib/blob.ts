import {
  BlobSASPermissions,
  BlobServiceClient,
  generateBlobSASQueryParameters,
} from "@azure/storage-blob";
import { DefaultAzureCredential } from "@azure/identity";

function getBlobServiceClient(): BlobServiceClient {
  const accountName = process.env.AZURE_STORAGE_ACCOUNT_NAME;
  if (!accountName) {
    throw new Error("AZURE_STORAGE_ACCOUNT_NAME is not set");
  }
  const credential = new DefaultAzureCredential();
  return new BlobServiceClient(
    `https://${accountName}.blob.core.windows.net`,
    credential,
  );
}

/**
 * Upload a document file to the raw-artifacts container.
 * Returns the blob path: raw-artifacts/{engagementId}/{fileName}
 */
export async function uploadEngagementFile(
  engagementId: string,
  fileName: string,
  buffer: Buffer,
  contentType: string,
): Promise<string> {
  const container =
    process.env.AZURE_STORAGE_CONTAINER_ENGAGEMENTS ?? "raw-artifacts";
  const client = getBlobServiceClient();
  const containerClient = client.getContainerClient(container);
  const blobName = `${engagementId}/${fileName}`;
  const blockBlobClient = containerClient.getBlockBlobClient(blobName);
  await blockBlobClient.upload(buffer, buffer.length, {
    blobHTTPHeaders: { blobContentType: contentType },
  });
  return `${container}/${blobName}`;
}

/**
 * Upload a generated deliverable to the deliverables container.
 * Returns the blob path: deliverables/{engagementId}/{fileName}
 */
export async function uploadDeliverable(
  engagementId: string,
  fileName: string,
  content: string,
): Promise<string> {
  const client = getBlobServiceClient();
  const containerClient = client.getContainerClient("deliverables");
  const blobName = `${engagementId}/${fileName}`;
  const blockBlobClient = containerClient.getBlockBlobClient(blobName);
  const buffer = Buffer.from(content, "utf-8");
  await blockBlobClient.upload(buffer, buffer.length, {
    blobHTTPHeaders: { blobContentType: "text/markdown; charset=utf-8" },
  });
  return `deliverables/${blobName}`;
}

/**
 * Delete a blob by its full path (container/blobName).
 * 404 is treated as success — blob is already gone.
 */
export async function deleteBlob(blobPath: string): Promise<void> {
  const client = getBlobServiceClient();
  const slashIndex = blobPath.indexOf("/");
  if (slashIndex === -1) return;
  const containerName = blobPath.slice(0, slashIndex);
  const blobName = blobPath.slice(slashIndex + 1);
  const containerClient = client.getContainerClient(containerName);
  const blockBlobClient = containerClient.getBlockBlobClient(blobName);
  try {
    await blockBlobClient.delete();
  } catch (err: unknown) {
    const code = (err as { statusCode?: number })?.statusCode;
    if (code === 404) return;
    throw err;
  }
}

/**
 * Delete an entire container by name (e.g. the per-engagement client portal
 * container `portal-<engagementId>`). Best-effort: a missing container (404) is
 * treated as success so callers can invoke this during engagement teardown
 * without knowing whether a portal was ever published (DATA-001 / C6).
 */
export async function deleteContainer(containerName: string): Promise<void> {
  if (!containerName) return;
  const client = getBlobServiceClient();
  const containerClient = client.getContainerClient(containerName);
  try {
    await containerClient.delete();
  } catch (err: unknown) {
    const code = (err as { statusCode?: number })?.statusCode;
    if (code === 404) return;
    throw err;
  }
}

/**
 * Generate a user-delegation SAS URL for a blob.
 * Returns a time-limited read-only URL valid for ttlHours (default 1 hour).
 */
export async function generateSasUrl(
  blobPath: string,
  ttlHours: number = 1,
): Promise<string> {
  const accountName = process.env.AZURE_STORAGE_ACCOUNT_NAME;
  if (!accountName) {
    throw new Error("AZURE_STORAGE_ACCOUNT_NAME is not set");
  }
  const client = getBlobServiceClient();
  const slashIndex = blobPath.indexOf("/");
  if (slashIndex === -1) throw new Error(`Invalid blobPath: ${blobPath}`);
  const containerName = blobPath.slice(0, slashIndex);
  const blobName = blobPath.slice(slashIndex + 1);

  const startsOn = new Date();
  const expiresOn = new Date(Date.now() + ttlHours * 3600 * 1000);

  const userDelegationKey = await client.getUserDelegationKey(startsOn, expiresOn);

  const sasParams = generateBlobSASQueryParameters(
    {
      containerName,
      blobName,
      permissions: BlobSASPermissions.parse("r"),
      startsOn,
      expiresOn,
    },
    userDelegationKey,
    accountName,
  );

  return `https://${accountName}.blob.core.windows.net/${containerName}/${blobName}?${sasParams.toString()}`;
}
