import type { Metadata } from "next";
import { Errors } from "@/sections/Errors";

export const metadata: Metadata = { title: "Errors — RIMAL", description: "Seven defects found in our own work, two near-misses, two checks that passed for the wrong reason." };

export default function Page() {
  return <Errors />;
}
