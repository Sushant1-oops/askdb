import type { ReactNode } from "react";

function inline(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith("**") && part.endsWith("**") && part.length > 4 ? (
      <strong key={i} className="font-semibold text-foreground">
        {part.slice(2, -2)}
      </strong>
    ) : (
      part
    ),
  );
}

export function RichText({ text }: { text: string }) {
  const blocks: ReactNode[] = [];
  let paragraph: string[] = [];
  let bullets: string[] = [];

  const flushParagraph = () => {
    if (paragraph.length) blocks.push(<p key={blocks.length}>{inline(paragraph.join(" "))}</p>);
    paragraph = [];
  };
  const flushBullets = () => {
    if (bullets.length) {
      blocks.push(
        <ul key={blocks.length} className="list-disc space-y-1 pl-5">
          {bullets.map((b, i) => (
            <li key={i}>{inline(b)}</li>
          ))}
        </ul>,
      );
    }
    bullets = [];
  };

  for (const raw of text.split("\n")) {
    const line = raw.trim();
    const bullet = /^[-*•]\s+(.*)$/.exec(line);
    if (!line) {
      flushParagraph();
      flushBullets();
    } else if (bullet?.[1] !== undefined) {
      flushParagraph();
      bullets.push(bullet[1]);
    } else {
      flushBullets();
      paragraph.push(line);
    }
  }
  flushParagraph();
  flushBullets();

  return <div className="space-y-2 text-sm leading-relaxed text-foreground/90">{blocks}</div>;
}
