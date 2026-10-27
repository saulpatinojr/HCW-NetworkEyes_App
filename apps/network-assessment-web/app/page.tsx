import { auth } from "@/lib/auth";
import { redirect } from "next/navigation";

// Root page — redirect authenticated users to dashboard, others to sign-in.
export default async function Home() {
  const session = await auth();
  if (session?.user) {
    redirect("/dashboard");
  }
  redirect("/auth/signin");
}
