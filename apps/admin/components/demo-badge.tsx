import { Badge } from "@katoshop/ui/badge";

/** Selo obrigatório do painel: todo dado exibido é de demonstração. */
export function DemoBadge() {
  return (
    <Badge variant="outline" title="Loja demonstrativa: produtos, estoque e contas são de teste.">
      dados demo
    </Badge>
  );
}
