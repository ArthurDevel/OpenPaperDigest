"use client";

import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';

const EXAMPLES = `
# LaTeX Test Page

Backticked math should render:

- \`D = G = ({V_c, V_e}, {E_ec, E_ee})\`
- \`\\omega_c(e) = \\sum_{k} x_k\`

Dollar-delimited math should render:

- $D = G = ({V_c, V_e}, {E_ec, E_ee})$
- $\\omega_c(e) = \\sum_{k} x_k$

Fenced blocks should render:

~~~math
\\int_0^1 x^2 \\, dx = 1/3
~~~
`;

export default function LatexTestPage() {
  try { console.log('[LT] render test page'); } catch {}
  const processed = React.useMemo(() => {
    // Simplest approach: convert backticked segments that look like TeX into $...$
    const looksMath = (s: string) => /[{}_^\\]|\\[a-zA-Z]+/.test(s);
    const out = EXAMPLES.replace(/`([^`]+)`/g, (m, inner) => {
      return looksMath(inner) ? `$${inner}$` : m;
    });
    try { console.log('[LT] preprocessed markdown', out); } catch {}
    return out;
  }, []);
  return (
    <div className="p-6 prose dark:prose-invert max-w-none">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[[rehypeKatex, { strict: false, throwOnError: false }]]}
      >
        {processed}
      </ReactMarkdown>
    </div>
  );
}


