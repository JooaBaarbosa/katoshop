import "server-only";
import { ApiProblem, unwrap } from "@katoshop/api-client";
import { notFound } from "next/navigation";
import { promotions } from "./api";
import { isCouponId, type Coupon } from "./coupons";
import { authed } from "./guard";
import { messageFor } from "./problem-messages";

export type CouponQuery = { q?: string; active?: boolean; cursor?: string };

export const INVALID_CURSOR = "promotions.pagination.invalid_cursor";

export function listCoupons(query: CouponQuery, limit = 24) {
  return authed(async (token) =>
    unwrap(
      await promotions(token).GET("/v1/admin/coupons", {
        params: { query: { ...query, limit } },
      }),
    ),
  );
}

export type CouponPage = Awaited<ReturnType<typeof listCoupons>>;

/**
 * Página da lista. Cursor adulterado ou vencido (422 `invalid_cursor`) cai na primeira página
 * com os mesmos filtros e um aviso; os outros erros sobem para a página de erro.
 */
export async function loadCouponList(
  query: CouponQuery,
): Promise<{ page: CouponPage; notice: string | null }> {
  try {
    return { page: await listCoupons(query), notice: null };
  } catch (error) {
    if (!(error instanceof ApiProblem) || error.code !== INVALID_CURSOR || !query.cursor) {
      throw error;
    }
    const firstPage: CouponQuery = {
      ...(query.q !== undefined ? { q: query.q } : {}),
      ...(query.active !== undefined ? { active: query.active } : {}),
    };
    return { page: await listCoupons(firstPage), notice: messageFor(INVALID_CURSOR) };
  }
}

/** Id que não é UUID, 404 ou 422 viram a página "não encontrado" (o id inválido nem sai daqui). */
export async function getCoupon(id: string): Promise<Coupon> {
  if (!isCouponId(id)) notFound();
  try {
    return await authed(async (token) =>
      unwrap(
        await promotions(token).GET("/v1/admin/coupons/{coupon_id}", {
          params: { path: { coupon_id: id } },
        }),
      ),
    );
  } catch (error) {
    if (error instanceof ApiProblem && (error.status === 404 || error.status === 422)) notFound();
    throw error;
  }
}
