export interface Figure {
  figure_identifier: string;
  short_id?: string;
  location_page: number;
  explanation: string;
  image_path: string;
  image_data_url: string;
  referenced_on_pages: number[];
  bounding_box: [number, number, number, number];
  page_image_size: [number, number];
}

export interface Page {
  page_number: number;
  image_data_url: string;
}

export interface Table {
  table_identifier: string;
  location_page: number;
  explanation: string;
  image_path: string;
  image_data_url: string;
  referenced_on_pages: number[];
  bounding_box: [number, number, number, number];
  page_image_size: [number, number];
}

export interface Section {
  level: number;
  section_title: string;
  start_page: number;
  end_page: number;
  rewritten_content: string | null;
  summary: string | null;
  subsections: Section[];
}

export interface Paper {
  paper_id: string;
  title: string | null;
  authors?: string | null;
  arxiv_url?: string | null;
  thumbnail_data_url?: string | null;
  five_minute_summary?: string | null;
  final_markdown?: string | null;
  sections: Section[];
  tables: Table[];
  figures: Figure[];
  pages: Page[];
  usage_summary?: {
    currency: 'USD';
    total_cost: number;
    total_prompt_tokens: number;
    total_completion_tokens: number;
    total_tokens: number;
    by_model: Record<string, {
      num_calls: number;
      total_cost: number;
      prompt_tokens: number;
      completion_tokens: number;
      total_tokens: number;
    }>;
  };
  processing_time_seconds?: number;
}

export interface JobStatusResponse {
  job_id: string;
  status: 'processing' | 'completed' | 'failed';
  result?: Paper; // The result is optional, as it's only present when the job is 'completed'
} 

export interface MinimalPaperItem {
  paper_uuid: string;
  title: string | null;
  authors: string | null;
  thumbnail_url: string | null;
  slug: string | null;
}