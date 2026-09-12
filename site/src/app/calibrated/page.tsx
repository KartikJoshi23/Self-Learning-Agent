import type { Metadata } from "next";
import { Calibrated } from "@/sections/Calibrated";

export const metadata: Metadata = { title: "Calibration — RIMAL", description: "Before any agent was trained, the simulator had to reproduce the literature." };

export default function Page() {
  return <Calibrated />;
}
