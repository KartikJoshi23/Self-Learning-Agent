import type { Metadata } from "next";
import { Learnt } from "@/sections/Learnt";

export const metadata: Metadata = { title: "Learning — RIMAL", description: "What PPO, a fleet estimator and QR-DQN actually learnt on this benchmark." };

export default function Page() {
  return <Learnt />;
}
