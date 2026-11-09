"use client";

// Read-only Python (or JSON) with line numbers, coloured as VS Code does (lib/flow/pycolor.ts; the
// colours are the --py-* CSS variables of studio.css), the error line marked. Built as React text
// spans: never innerHTML (gamefile.test.ts scans src/ for it).
//
// Ported from MatPilot (https://github.com/lumduan/matpilot at commit d639909,
// src/components/blocks/CodeView.tsx; THIRD_PARTY.md), MIT License, Copyright (c) 2026 Sarat
// Sonsuk. Permission is hereby granted, free of charge, to any person obtaining a copy of this
// software and associated documentation files (the "Software"), to deal in the Software without
// restriction, including without limitation the rights to use, copy, modify, merge, publish,
// distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the
// Software is furnished to do so, subject to the following conditions: The above copyright notice
// and this permission notice shall be included in all copies or substantial portions of the
// Software. THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE
// AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
// DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
// OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
// Changed here: the colours come synchronously from our own tokenizer (no lazy @lezer import), no
// "AI helper" mark, and a `colour` switch (JSON is shown plain).
import { forwardRef, useMemo } from "react";

import { colouredPieces } from "@/lib/flow/pycolor";

export type CodeViewProps = {
  code: string;
  errorLine?: number | null;
  label?: string;
  colour?: boolean;
  testId?: string;
};

const CodeView = forwardRef<HTMLPreElement, CodeViewProps>(function CodeView(
  { code, errorLine = null, label = "Python made from the blocks", colour = true, testId = "python-code" },
  ref,
) {
  const pieces = useMemo(() => (colour ? colouredPieces(code) : null), [code, colour]);
  const lines = code === "" ? [""] : code.replace(/\n$/, "").split("\n");
  return (
    <div className="code-view" data-testid={testId}>
      <pre className="code-gutter" aria-hidden="true">
        {lines.map((_, i) => (
          <span key={i} className={i + 1 === errorLine ? "code-gutter-error" : undefined}>
            {i + 1}
            {"\n"}
          </span>
        ))}
      </pre>
      <pre className="code-text" tabIndex={0} aria-label={label} ref={ref}>
        {pieces
          ? pieces.map((piece, i) =>
              piece.kind ? (
                <span key={i} className={`py-${piece.kind}`}>
                  {piece.text}
                </span>
              ) : (
                piece.text
              ),
            )
          : code}
      </pre>
    </div>
  );
});

export default CodeView;
