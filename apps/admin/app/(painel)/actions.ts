"use server";

import { redirect } from "next/navigation";
import { endSession } from "../../lib/sign-out";

export async function logoutAction(): Promise<void> {
  await endSession();
  redirect("/entrar");
}
