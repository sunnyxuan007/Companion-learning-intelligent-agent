"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function VolunteerTableRedirect() {
  const router = useRouter();
  useEffect(() => { router.replace("/volunteer"); }, [router]);
  return <div className="p-6 text-sm text-gray-400">正在跳转到志愿填报页面…</div>;
}
