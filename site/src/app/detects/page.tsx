import type { Metadata } from "next";
import { Detects } from "@/sections/Detects";

export const metadata: Metadata = { title: "Detection — RIMAL", description: "The plant never sees soiling; a Kalman filter recovers it from a noisy performance ratio." };

export default function Page() {
  return <Detects />;
}
