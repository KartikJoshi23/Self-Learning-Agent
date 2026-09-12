import type { Metadata } from "next";
import { Reproduce } from "@/sections/Reproduce";

export const metadata: Metadata = { title: "Reproduce — RIMAL", description: "A clean clone reproduces the record from an empty cache." };

export default function Page() {
  return <Reproduce />;
}
