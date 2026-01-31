import { redirect } from 'next/navigation';

interface PageProps {
  params: {
    slug: string;
  };
}

/**
 * Redirects from sharedpaper/[slug] to paper/[slug]
 * @param params - Page parameters containing the slug
 */
export default function SharedPaperRedirect({ params }: PageProps) {
  redirect(`/paper/${params.slug}`);
}

