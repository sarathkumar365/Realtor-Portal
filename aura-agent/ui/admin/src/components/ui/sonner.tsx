import { Toaster as Sonner } from "sonner";

export function Toaster() {
  return (
    <Sonner position="bottom-center" closeButton
      toastOptions={{ className: "!rounded-full !border-line !bg-raise !text-foreground !font-mono !text-[12px]" }} />
  );
}
