import { Navigate, type RouteObject } from "react-router";

import { RequireAdmin } from "@/features/auth/RequireAdmin";
import { SignInPage } from "@/features/auth/SignInPage";
import { HomePage } from "@/features/home/HomePage";
import { JobDetailPage } from "@/features/jobs/JobDetailPage";
import { JobListPage } from "@/features/jobs/JobListPage";
import { UnbrandingSettingsPage } from "@/features/jobs/UnbrandingSettingsPage";
import { UploadPage } from "@/features/jobs/UploadPage";
import { MarkPage } from "@/features/organization/MarkPage";
import { OrganizationPage } from "@/features/organization/OrganizationPage";

import { AppShell } from "./layout/AppShell";
import { SettingsLayout } from "./layout/SettingsLayout";
import { RouteError } from "./RouteError";

/** Every route in one place. Everything but sign-in is behind RequireAdmin, and
 * each screen has the error boundary, so one screen failing leaves the shell. */
export const routes: RouteObject[] = [
  { path: "/sign-in", element: <SignInPage />, errorElement: <RouteError /> },
  {
    element: (
      <RequireAdmin>
        <AppShell />
      </RequireAdmin>
    ),
    errorElement: <RouteError />,
    children: [
      {
        errorElement: <RouteError />,
        children: [
          { index: true, element: <HomePage /> },
          { path: "/jobs", element: <JobListPage /> },
          { path: "/jobs/new", element: <UploadPage /> },
          { path: "/jobs/:jobId", element: <JobDetailPage /> },
          {
            path: "/settings",
            element: <SettingsLayout />,
            children: [
              { index: true, element: <Navigate to="/settings/organization" replace /> },
              { path: "organization", element: <OrganizationPage /> },
              { path: "organization/mark", element: <MarkPage /> },
              { path: "unbranding", element: <UnbrandingSettingsPage /> },
            ],
          },
          // Where Organization lived before Settings had sections.
          { path: "/organization", element: <Navigate to="/settings/organization" replace /> },
          { path: "/organization/mark", element: <Navigate to="/settings/organization/mark" replace /> },
          { path: "*", element: <Navigate to="/" replace /> },
        ],
      },
    ],
  },
];
