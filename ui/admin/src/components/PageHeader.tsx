import { Fragment, type ReactNode } from "react";
import { Link } from "react-router";

/** The title row of a screen: a title, an optional line under it, actions on the right. */
export function PageHeader({ eyebrow, trail, title, mark, description, actions }: {
  /** A small label above the title: where the screen sits ("Capabilities"). */
  eyebrow?: string;
  /** The way back, above the title: the screens above this one, each a link, then this one. */
  trail?: { label: string; to: string }[];
  title: string;
  /** A small marker beside the title: a mode the whole screen is in ("Test mode"). */
  mark?: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="mb-8 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        {eyebrow && <div className="label-caps mb-2.5">{eyebrow}</div>}
        {trail && (
          <nav aria-label="Breadcrumb" className="label-caps mb-2.5 flex flex-wrap items-center gap-2">
            {trail.map(({ label, to }) => (
              <Fragment key={to}>
                <Link to={to} className="transition-colors hover:text-fg-2">{label}</Link>
                <span aria-hidden>/</span>
              </Fragment>
            ))}
            <span aria-current="page" className="text-fg-2">{title}</span>
          </nav>
        )}
        {mark ? <div className="flex flex-wrap items-center gap-3"><h1>{title}</h1>{mark}</div> : <h1>{title}</h1>}
        {description && <p className="mt-2 max-w-[62ch] text-fg-2">{description}</p>}
      </div>
      {actions && <div className="flex max-w-full flex-wrap gap-2">{actions}</div>}
    </header>
  );
}
