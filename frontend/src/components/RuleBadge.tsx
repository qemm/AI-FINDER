const SEVERITY: Record<string, { bg: string; color: string }> = {
  // Critical — leaked AI API keys
  openai_api_key: { bg: "#f38ba8", color: "#1e1e2e" },
  anthropic_api_key: { bg: "#f38ba8", color: "#1e1e2e" },
  aws_access_key: { bg: "#f38ba8", color: "#1e1e2e" },
  // High
  github_token: { bg: "#fab387", color: "#1e1e2e" },
  huggingface_token: { bg: "#fab387", color: "#1e1e2e" },
  langsmith_api_key: { bg: "#fab387", color: "#1e1e2e" },
  // Medium
  hardcoded_secret: { bg: "#f9e2af", color: "#1e1e2e" },
  high_entropy_string: { bg: "#f9e2af", color: "#1e1e2e" },
  // Info / default
  _default: { bg: "#585b70", color: "#cdd6f4" },
};

interface RuleBadgeProps {
  ruleName: string;
}

export function RuleBadge({ ruleName }: RuleBadgeProps) {
  const style = SEVERITY[ruleName] ?? SEVERITY["_default"];
  return (
    <span
      style={{
        display: "inline-block",
        padding: "0.15em 0.55em",
        borderRadius: "4px",
        fontSize: "0.75rem",
        fontWeight: 600,
        background: style.bg,
        color: style.color,
        whiteSpace: "nowrap",
      }}
    >
      {ruleName}
    </span>
  );
}
