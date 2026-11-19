import "server-only";
import { ApiProblem, unwrap } from "@katoshop/api-client";
import { notFound } from "next/navigation";
import { promotions } from "./api";
import type { Coupon } from "./coupons";
import { authed } from "./guard";

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

/** 404 (ou id malformado, 422) vira a página "não encontrado". */
export async function getCoupon(id: string): Promise<Coupon> {
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
