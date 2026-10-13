# Components

Every shared component in `src/components/`, what it is for and when to reach
for it. **Read this before writing a component.** If one here does the job, use
it; if one almost does, extend it here rather than copy it into a feature.

A test (`src/components/registry.test.ts`) fails when a file in `src/components/`
(outside `ui/`) has no `###` entry below, named after the file.

## Primitives — `src/components/ui/`

shadcn-style wrappers over Radix and Tailwind, themed with the brand tokens. No
app logic. Import from `@/components/ui/<name>`.

| Primitive | Use |
|---|---|
| `Button` | Every clickable action. `variant`: primary (default), secondary, ghost, danger. `size`: sm, md, lg, icon. `asChild` to style a link as a button. Defaults to `type="button"`; pass `type="submit"` in forms. |
| `Input` | Single-line text. Shows the danger border when `aria-invalid` is set (FormField sets it). |
| `Label` | A form label. Prefer `FormField`, which wires it up. |
| `Card` | A white panel with a border: a form, a summary block. |
| `Badge` | A short status or tag. `tone`: neutral, info, success, warning, danger. Map a domain status to a tone in the feature (see `features/jobs/model.ts`), not here. |
| `Table` (+ `TableHead`, `TableBody`, `TableRow`, `TableHeader`, `TableCell`) | A list people scan by column. Wraps itself in a scrolling bordered box. |
| `Tabs` (+ `TabsList`, `TabsTrigger`, `TabsContent`) | Switching between views or filters of one list. Radix handles arrow keys. |
| `Progress` | A bar for work with a known share done (an upload). Requires a `label` for screen readers. |
| `Skeleton` | A grey placeholder where content will appear. |
| `Textarea` | Multi-line text, styled like `Input`. |
| `Toaster` | Mounted once in `App`. Call `toast.error(...)` / `toast.success(...)` from `sonner` for results that need no place on the page (a download failed, a profile saved). |

## Shared — `src/components/`

### AuthImage
An image that needs the bearer token: `load(signal)` returns a `Blob` (a function
from `api/`), `queryKey` caches it. Loads when scrolled within 400px, at most 4 at
once across the page; skeleton, then the image, or a placeholder with Retry.
Revokes its object URL when it goes. Use it for every image Aura serves.

### BrandMark
The gold Aura Key monogram as inline SVG. Decorative (`aria-hidden`): always put
the product name beside it in text. Size it with a height class: `<BrandMark className="h-6" />`.

### ColourField
A `#RRGGBB` colour: a swatch picker beside a hex text box, kept in step. Controlled
(`value`, `onChange`); with react-hook-form use a `Controller`. Goes inside
`FormField`, which labels the text box.

### ConfirmDialog
Asks before something that cannot be taken back: `open`, `title`, `description`,
`confirmLabel`, `onConfirm`, `onCancel`. Used for leaving a form with unsaved
changes (with react-router's `useBlocker`).

### DownloadButton
A button that runs `onDownload` (usually `download(path, fallbackName)` from
`api/download`), is disabled while it runs, and shows a toast with the reason if
it fails.

### EmptyState
A list with nothing in it: `title`, what it would hold, and an `action` to fill it.

### ErrorState
A failed load: what went wrong in words and, with `onRetry`, a "Try again" button.
Pass the error from a query as is; it reads `ApiError.message` and shows the
offline icon for `offline` and `timeout`. Use it for every query's error branch:
`if (query.isError) return <ErrorState error={query.error} onRetry={query.refetch} />`.

### FileDropzone
Drop or pick files; lists them with size, a remove button, and a problem per file
from `problems` (by index). It does not check files: the caller does (for PDFs,
`lib/pdfCheck.ts`) and passes the problems back. Rejected drops are kept in the
list so the caller can say why, never dropped silently.

### FormField
A label, exactly one control and its error or hint. Gives the control its `id`,
`aria-invalid` and `aria-describedby`. Use it for every field in every form:
`<FormField label="City" error={errors.city?.message}><Input {...register("city")} /></FormField>`.

### KeyValueList
Labelled facts in a responsive grid: the summary block of a record.

### LoadingState
A spinner with words for an area still loading. For a list or a page, not a
button (a pending button changes its own label).

### OfflineBanner
Mounted once in the shell. Shows while the browser reports it is offline.

### PageHeader
The title row of every screen: `title`, optional `description`, `actions` on
the right (buttons). Every routed page starts with one.

### Timeline
What happened, oldest first: `items` of `{ id, when, title, detail? }`. The caller
formats `when` (with `lib/format.ts`).
