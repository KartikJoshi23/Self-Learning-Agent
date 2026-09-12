import type { Metadata } from "next";
import { Simulate } from "@/sections/Simulate";

export const metadata: Metadata = { title: "Simulator — RIMAL", description: "Run the plant live: the same physics, rules and trained policy in your browser." };

export default function Page() {
  return <Simulate />;
}
