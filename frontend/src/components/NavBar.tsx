import { NavLink } from "react-router-dom";

const links = [
  { to: "/", label: "Dashboard" },
  { to: "/jobs/new", label: "New Job" },
  { to: "/files", label: "Files" },
  { to: "/secrets", label: "Secrets" },
  { to: "/search", label: "Semantic Search" },
];

export function NavBar() {
  return (
    <nav style={navStyle}>
      <span style={brandStyle}>AI-FINDER</span>
      <div style={linksStyle}>
        {links.map(({ to, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            style={({ isActive }) => ({ ...linkStyle, fontWeight: isActive ? 700 : 400 })}
          >
            {label}
          </NavLink>
        ))}
      </div>
    </nav>
  );
}

const navStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: "2rem",
  padding: "0.75rem 1.5rem",
  background: "#1e1e2e",
  borderBottom: "1px solid #313244",
};

const brandStyle: React.CSSProperties = {
  fontWeight: 800,
  fontSize: "1.1rem",
  color: "#cba6f7",
  letterSpacing: "0.05em",
};

const linksStyle: React.CSSProperties = {
  display: "flex",
  gap: "1rem",
};

const linkStyle: React.CSSProperties = {
  color: "#cdd6f4",
  textDecoration: "none",
  fontSize: "0.9rem",
};
