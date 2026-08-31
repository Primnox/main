/* AAD context strings — one source of truth for what binds each ciphertext to
   its place (CRS/1.0-W §5). The seal side (turn driver, vault) and the open
   side (event feed) both import from here; any drift is a decryption failure
   by construction, which is the point. */

export const aadFor = {
  /** an event payload, bound to its (client-generated) event id + kind */
  event: (eventId: string, kind: string): string => `evt:${eventId}/${kind}`,
  /** a message body row */
  message: (msgId: string): string => `msg:${msgId}/body`,
  /** the provider-key bundle in the vault */
  providerKeys: (): string => 'vault:provider-keys/v1',
  /** a memory entry */
  memory: (memId: string): string => `mem:${memId}/text`,
  /** a memory entry's embedding vector */
  memoryVector: (memId: string): string => `mem:${memId}/vec`,
  /** one CRDT update for a workspace canvas */
  canvasUpdate: (workspaceId: string, seq: number): string => `canvas:${workspaceId}/${seq}`,
  /** a workspace version's file map */
  workspaceVersion: (workspaceId: string, version: number): string => `ws:${workspaceId}/v${version}`,
  /** an asset's extracted text */
  assetText: (assetId: string): string => `asset:${assetId}/text`,
} as const;
