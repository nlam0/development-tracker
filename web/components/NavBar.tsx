import Link from "next/link";

const LINKS = [
  { href: "/", label: "Feed" },
  { href: "/map", label: "Map" },
  { href: "/watchlist", label: "Watchlist" },
  { href: "/methodology", label: "Methodology" },
];

export default function NavBar() {
  return (
    <header className="border-b border-border bg-surface">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
        <Link href="/" className="text-sm font-semibold tracking-tight">
          Lower Manhattan Development Tracker
        </Link>
        <nav className="flex gap-5 text-sm text-muted">
          {LINKS.map((link) => (
            <Link key={link.href} href={link.href} className="hover:text-foreground">
              {link.label}
            </Link>
          ))}
        </nav>
      </div>
    </header>
  );
}
