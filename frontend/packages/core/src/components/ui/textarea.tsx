import * as React from "react";

import { cn } from "@chimera/core/lib/utils";

/**
 * Renders a styled textarea element whose classes are merged with any provided `className`.
 *
 * @param className - Additional CSS classes to append to the component's default classes
 * @param props - Other standard textarea attributes forwarded to the underlying element
 * @returns A JSX `textarea` element with `data-slot="textarea"`, composed classes, and the forwarded props
 */
function Textarea({ className, ...props }: React.ComponentProps<"textarea">) {
  return (
    <textarea
      data-slot="textarea"
      className={cn(
        "border-input placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-ring/50 aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 aria-invalid:border-destructive dark:bg-input/30 flex field-sizing-content min-h-16 w-full rounded-md border bg-transparent px-3 py-2 text-base shadow-xs transition-[color,box-shadow] outline-hidden focus-visible:ring-[3px] disabled:cursor-not-allowed disabled:opacity-50 md:text-sm",
        className
      )}
      {...props}
    />
  );
}

export { Textarea };
