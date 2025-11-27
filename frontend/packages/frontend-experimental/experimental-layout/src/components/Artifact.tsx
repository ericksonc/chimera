import {
  Artifact as ArtifactContainer,
  ArtifactHeader,
  ArtifactTitle,
  ArtifactContent,
} from "@chimera/core/components/ai-elements/artifact";

export function Artifact() {
  return (
    <ArtifactContainer className="h-full border-0 rounded-none shadow-none">
      <ArtifactHeader className="bg-transparent px-4 py-2 border-b">
        <ArtifactTitle>State Machine</ArtifactTitle>
      </ArtifactHeader>
      <ArtifactContent className="p-4">
        <div className="text-sm text-muted-foreground">
          Placeholder for state machine visualization.
        </div>
      </ArtifactContent>
    </ArtifactContainer>
  );
}
