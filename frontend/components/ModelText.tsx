import { Fragment } from "react";
import { parseModelText, type Block, type Inline } from "@/lib/modelText";

// Renders model or retrieved text with the safe markdown subset from lib/modelText.ts. Used by
// the answer card (Assistant) and later the study notes and plan text. Only fixed React elements
// with fixed classes come out: no HTML string, no href, no attributes taken from the text.

function Inlines({ items }: { items: Inline[] }) {
  return (
    <>
      {items.map((item, i) => {
        if (item.kind === "code") {
          return (
            <code key={i} className="rounded-sm bg-sunken px-1 font-mono text-[0.9em] break-words">
              {item.text}
            </code>
          );
        }
        if (item.kind === "strong") {
          return (
            <strong key={i} className="font-semibold">
              <Inlines items={item.children} />
            </strong>
          );
        }
        return <Fragment key={i}>{item.text}</Fragment>;
      })}
    </>
  );
}

function BlockView({ block }: { block: Block }) {
  switch (block.kind) {
    case "heading":
      // A bold line, not an <h*>: model text must not break the page's heading outline.
      return (
        <p className="font-semibold">
          <Inlines items={block.inlines} />
        </p>
      );
    case "code":
      return (
        <pre className="rounded-sm border border-rule bg-sunken p-3 font-mono text-small whitespace-pre-wrap break-words">
          <code>{block.text}</code>
        </pre>
      );
    case "list": {
      const items = block.items.map((item, i) => (
        <li key={i}>
          <Inlines items={item} />
        </li>
      ));
      return block.ordered ? (
        <ol start={block.start} className="list-decimal space-y-1 pl-6">
          {items}
        </ol>
      ) : (
        <ul className="list-disc space-y-1 pl-6">{items}</ul>
      );
    }
    case "paragraph":
      return (
        <p>
          {block.lines.map((line, i) => (
            <Fragment key={i}>
              {i > 0 && <br />}
              <Inlines items={line} />
            </Fragment>
          ))}
        </p>
      );
  }
}

export function ModelText({ text, className = "" }: { text: string; className?: string }) {
  return (
    <div className={`space-y-3 ${className}`}>
      {parseModelText(text).map((block, i) => (
        <BlockView key={i} block={block} />
      ))}
    </div>
  );
}
