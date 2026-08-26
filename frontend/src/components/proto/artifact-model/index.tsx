/**
 * Unit 6 Artifact Model Prototype
 *
 * Research vehicle to test unified Artifact interface
 * Port 5306
 */

export { ArtifactModelDemo } from './demo';
export type { Artifact, ArtifactKind, ArtifactType, ArtifactStatus } from './types';
export { workspaceToArtifact, pdfAssetToArtifact, slideAssetToArtifact, imageAssetToArtifact } from './converters';
