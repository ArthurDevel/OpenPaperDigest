import { redirect } from 'next/navigation';

interface PageProps {
  params: Promise<{
    slug: string;
  }>;
}

/**
 * Redirects from sharedpaper/[slug] to paper/[slug]
 * @param params - Page parameters containing the slug
 */
export default async function SharedPaperRedirect({ params }: PageProps) {
  const resolvedParams = await params;
  redirect(`/paper/${resolvedParams.slug}`);
}

