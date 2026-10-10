import { signIn } from "@/lib/auth";

export default function SignInPage() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center px-4">
      {/* Glass card */}
      <div className="glass w-full max-w-sm p-8">
        {/* Logo */}
        {/* W3C-01 / W3C-12: picture tag with prefers-color-scheme prevents duplicate downloads and CLS */}
        <picture>
          <source
            srcSet="/cbts-logo-bright-teal.svg"
            media="(prefers-color-scheme: dark)"
          />
          <img
            src="/cbts-logo-dark-teal.svg"
            alt="CBTS"
            className="mb-6 h-9 w-auto"
            width={108}
            height={36}
          />
        </picture>

        <h1 className="mb-1 text-2xl font-black tracking-tight text-navy-800 dark:text-navy-50">
          Cloud Network Assessment
        </h1>
        <p className="mb-8 text-sm text-navy-400 dark:text-navy-200">
          Sign in with your CBTS Microsoft account to continue.
        </p>

        <form
          action={async () => {
            "use server";
            await signIn("microsoft-entra-id", { redirectTo: "/" });
          }}
        >
          <button type="submit" className="btn-teal w-full justify-center py-2.5 text-sm">
            <svg aria-hidden="true" focusable="false" className="h-4 w-4" viewBox="0 0 21 21" fill="none" xmlns="http://www.w3.org/2000/svg">
              <rect x="1"  y="1"  width="9" height="9" fill="#f25022" />
              <rect x="11" y="1"  width="9" height="9" fill="#7fba00" />
              <rect x="1"  y="11" width="9" height="9" fill="#00a4ef" />
              <rect x="11" y="11" width="9" height="9" fill="#ffb900" />
            </svg>
            Sign in with Microsoft
          </button>
        </form>
      </div>

      <p className="mt-6 text-xs text-navy-400 dark:text-navy-300">
        CBTS Internal Platform · Restricted Access
      </p>
    </div>
  );
}
