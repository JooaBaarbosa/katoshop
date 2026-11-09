import { Button } from "@katoshop/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@katoshop/ui/dialog";
import { Ruler } from "lucide-react";
import { SIZE_GUIDE_NOTE, sizeGuideFor } from "../content/size-guide";

export function SizeGuideDialog({ categorySlug }: { categorySlug: string }) {
  const tables = sizeGuideFor(categorySlug);
  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button type="button" variant="ghost" className="h-auto px-0 py-1 normal-case underline underline-offset-4">
          <Ruler aria-hidden className="size-4" />
          Guia de medidas
        </Button>
      </DialogTrigger>
      <DialogContent className="max-h-[90dvh] w-[calc(100%-2rem)] max-w-2xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Guia de medidas</DialogTitle>
          <DialogDescription>{SIZE_GUIDE_NOTE}</DialogDescription>
        </DialogHeader>
        {tables.map((table) => (
          <div key={table.title} className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <caption className="mb-2 text-left font-display text-lg">{table.title}</caption>
              <thead>
                <tr className="border-b border-ks-border text-xs uppercase tracking-wide text-ks-muted">
                  <th scope="col" className="py-2 pr-4 font-semibold">
                    Tamanho
                  </th>
                  {table.measures.map((measure) => (
                    <th key={measure} scope="col" className="py-2 pr-4 font-semibold">
                      {measure} (cm)
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {table.rows.map((row) => (
                  <tr key={row.size} className="border-b border-ks-border last:border-0">
                    <th scope="row" className="py-2 pr-4 font-semibold">
                      {row.size}
                    </th>
                    {row.values.map((value, index) => (
                      <td key={table.measures[index]} className="py-2 pr-4 font-mono">
                        {value}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))}
      </DialogContent>
    </Dialog>
  );
}
