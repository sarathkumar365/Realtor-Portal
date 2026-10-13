import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Navigate, useLocation, useNavigate } from "react-router";
import { z } from "zod";

import { signIn, whoIs } from "@/api/auth";
import { ApiError, DEFAULT_MESSAGE } from "@/api/errors";
import { BrandMark } from "@/components/BrandMark";
import { FormField } from "@/components/FormField";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

import { getEndReason, startSession } from "./session";
import { useSession } from "./useSession";

const schema = z.object({
  user: z.string().trim().min(1, "Enter your portal ID"),
  password: z.string().min(1, "Enter your password"),
});
type Credentials = z.infer<typeof schema>;

class NotAdmin extends Error {}

/** Same portal ID and password as the realtor app; only admins get in. */
export function SignInPage() {
  const session = useSession();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from ?? "/jobs";
  const [notice] = useState(getEndReason);
  const form = useForm<Credentials>({ resolver: zodResolver(schema), defaultValues: { user: "", password: "" } });

  const attempt = useMutation({
    mutationFn: async ({ user, password }: Credentials) => {
      const signedIn = await signIn(user, password);
      // Checked by Aura with the new token before anything is kept: a realtor's
      // token never lands in this app's storage.
      const me = await whoIs(signedIn.token);
      if (!me.admin) throw new NotAdmin();
      return { token: signedIn.token, user: me.user, name: signedIn.name };
    },
    onSuccess: (signedIn) => {
      startSession(signedIn);
      navigate(from, { replace: true });
    },
  });

  if (session) return <Navigate to={from} replace />;

  const error = attempt.error;
  const message = error instanceof NotAdmin
    ? "This app is for admins. Your account does not have admin access."
    : error instanceof ApiError
      ? error.kind === "unauthorized" ? "Wrong portal ID or password." : error.message
      : error ? DEFAULT_MESSAGE.server : null;
  const errors = form.formState.errors;

  return (
    <main className="flex min-h-full items-center justify-center bg-sidebar p-6">
      <Card className="w-full max-w-sm">
        <div className="mb-6 flex flex-col items-center gap-2">
          <BrandMark className="h-10" />
          <h1 className="text-xl font-bold">Aura Agent</h1>
          <p className="text-sm text-muted">Sign in with your portal ID</p>
        </div>
        {notice && <p role="status" className="mb-4 rounded-lg bg-rule p-3 text-sm">{notice}</p>}
        <form noValidate onSubmit={form.handleSubmit((values) => attempt.mutate(values))} className="flex flex-col gap-4">
          <FormField label="Portal ID" error={errors.user?.message}>
            <Input autoComplete="username" autoFocus {...form.register("user")} />
          </FormField>
          <FormField label="Password" error={errors.password?.message}>
            <Input type="password" autoComplete="current-password" {...form.register("password")} />
          </FormField>
          {message && <p role="alert" className="text-sm text-danger">{message}</p>}
          <Button type="submit" size="lg" disabled={attempt.isPending}>
            {attempt.isPending ? "Signing in" : "Sign in"}
          </Button>
        </form>
      </Card>
    </main>
  );
}
