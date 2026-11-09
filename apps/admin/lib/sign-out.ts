import "server-only";
import { identity } from "./api";
import { getRefreshToken, session } from "./session";

/** Revoga o refresh token no identity (melhor esforço) e apaga os cookies da sessão. */
export async function endSession(): Promise<void> {
  const refreshToken = await getRefreshToken();
  if (refreshToken) {
    try {
      await identity().POST("/v1/auth/logout", { body: { refresh_token: refreshToken } });
    } catch {
      // a sessão local é encerrada mesmo se o identity estiver fora
    }
  }
  await session.clear();
}
