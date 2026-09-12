import type { Metadata } from "next";
import { Verdict } from "@/sections/Verdict";

export const metadata: Metadata = { title: "Verdict — RIMAL", description: "Four hypotheses, four negative results for deep RL; the finding that transfers." };

export default function Page() {
  return <Verdict />;
}
