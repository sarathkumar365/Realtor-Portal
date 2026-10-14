import { z } from "zod";

// Mirrors app/domain/organization.py in aura-chat, so a mistake is caught before
// Save; the server checks again and its 422 lands on the same fields.
const HEX_COLOUR = /^#[0-9A-Fa-f]{6}$/;
// Letters only, accented ones too: the mark is set letter by letter in a PDF font.
const LETTERS = /^\p{L}+$/u;

const number = (message: string) => z.number({ error: message });

export const brandSchema = z.object({
  mark_words: z.array(z.object({
    text: z.string().regex(LETTERS, "Letters only, one word"),
    colour: z.string().regex(HEX_COLOUR, "A colour like #C9A227"),
  })).min(1, "The mark needs at least one word"),
  font: z.enum(["Times", "Helvetica", "Courier"]),
  size: number("Enter a size in points").gt(0, "Must be more than 0"),
  tracking: number("Enter the spacing in points").min(0, "Cannot be negative"),
  opacity: number("Enter an opacity").gt(0, "Must be more than 0").max(1, "At most 1"),
  margin: number("Enter a margin in points").min(0, "Cannot be negative"),
});

export const organizationSchema = z.object({
  name: z.string().trim().min(1, "Enter the brokerage's name"),
  short_name: z.string().trim().min(1, "Enter a short name"),
  assistant_name: z.string().trim().min(1, "Enter the assistant's name"),
  region: z.string().trim().min(1, "Enter the region"),
  brand: brandSchema,
});

export type OrganizationForm = z.infer<typeof organizationSchema>;
export type BrandForm = z.infer<typeof brandSchema>;

// The two screens edit one profile in two parts: the brokerage's details, and its mark.
export const detailsSchema = organizationSchema.omit({ brand: true });
export type DetailsForm = z.infer<typeof detailsSchema>;
