export type Json =
  | string
  | number
  | boolean
  | null
  | { [key: string]: Json | undefined }
  | Json[]

export type Database = {
  // Allows to automatically instantiate createClient with right options
  // instead of createClient<Database, { PostgrestVersion: 'XX' }>(URL, KEY)
  __InternalSupabase: {
    PostgrestVersion: "14.1"
  }
  public: {
    Tables: {
      alembic_version: {
        Row: {
          version_num: string
        }
        Insert: {
          version_num: string
        }
        Update: {
          version_num?: string
        }
        Relationships: []
      }
      authors: {
        Row: {
          affiliations: Json | null
          citation_count: number | null
          created_at: string
          h_index: number | null
          homepage: string | null
          id: number
          name: string
          paper_count: number | null
          s2_author_id: string
          stats_updated_at: string | null
        }
        Insert: {
          affiliations?: Json | null
          citation_count?: number | null
          created_at?: string
          h_index?: number | null
          homepage?: string | null
          id?: number
          name: string
          paper_count?: number | null
          s2_author_id: string
          stats_updated_at?: string | null
        }
        Update: {
          affiliations?: Json | null
          citation_count?: number | null
          created_at?: string
          h_index?: number | null
          homepage?: string | null
          id?: number
          name?: string
          paper_count?: number | null
          s2_author_id?: string
          stats_updated_at?: string | null
        }
        Relationships: []
      }
      paper_authors: {
        Row: {
          author_id: number
          author_order: number
          id: number
          paper_id: number
        }
        Insert: {
          author_id: number
          author_order: number
          id?: number
          paper_id: number
        }
        Update: {
          author_id?: number
          author_order?: number
          id?: number
          paper_id?: number
        }
        Relationships: [
          {
            foreignKeyName: "paper_authors_author_id_fkey"
            columns: ["author_id"]
            isOneToOne: false
            referencedRelation: "authors"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "paper_authors_paper_id_fkey"
            columns: ["paper_id"]
            isOneToOne: false
            referencedRelation: "papers"
            referencedColumns: ["id"]
          },
        ]
      }
      paper_slugs: {
        Row: {
          created_at: string
          deleted_at: string | null
          id: number
          paper_uuid: string | null
          slug: string
          tombstone: boolean
        }
        Insert: {
          created_at: string
          deleted_at?: string | null
          id?: number
          paper_uuid?: string | null
          slug: string
          tombstone?: boolean
        }
        Update: {
          created_at?: string
          deleted_at?: string | null
          id?: number
          paper_uuid?: string | null
          slug?: string
          tombstone?: boolean
        }
        Relationships: []
      }
      paper_status_history: {
        Row: {
          date: string
          failed_count: number
          id: number
          not_started_count: number
          processed_count: number
          processing_count: number
          snapshot_at: string
          total_count: number
        }
        Insert: {
          date: string
          failed_count: number
          id?: number
          not_started_count: number
          processed_count: number
          processing_count: number
          snapshot_at?: string
          total_count: number
        }
        Update: {
          date?: string
          failed_count?: number
          id?: number
          not_started_count?: number
          processed_count?: number
          processing_count?: number
          snapshot_at?: string
          total_count?: number
        }
        Relationships: []
      }
      papers: {
        Row: {
          abstract: string | null
          arxiv_id: string | null
          arxiv_url: string | null
          arxiv_version: string | null
          authors: string | null
          avg_cost_per_page: number | null
          content_hash: string | null
          created_at: string
          embedding: string | null
          error_message: string | null
          external_popularity_signals: Json | null
          finished_at: string | null
          id: number
          initiated_by_user_id: string | null
          num_pages: number | null
          paper_uuid: string
          pdf_url: string | null
          processing_time_seconds: number | null
          signals: Json | null
          started_at: string | null
          status: string
          summaries: Json | null
          title: string | null
          total_cost: number | null
          updated_at: string
        }
        Insert: {
          abstract?: string | null
          arxiv_id?: string | null
          arxiv_url?: string | null
          arxiv_version?: string | null
          authors?: string | null
          avg_cost_per_page?: number | null
          content_hash?: string | null
          created_at?: string
          embedding?: string | null
          error_message?: string | null
          external_popularity_signals?: Json | null
          finished_at?: string | null
          id?: number
          initiated_by_user_id?: string | null
          num_pages?: number | null
          paper_uuid: string
          pdf_url?: string | null
          processing_time_seconds?: number | null
          signals?: Json | null
          started_at?: string | null
          status: string
          summaries?: Json | null
          title?: string | null
          total_cost?: number | null
          updated_at?: string
        }
        Update: {
          abstract?: string | null
          arxiv_id?: string | null
          arxiv_url?: string | null
          arxiv_version?: string | null
          authors?: string | null
          avg_cost_per_page?: number | null
          content_hash?: string | null
          created_at?: string
          embedding?: string | null
          error_message?: string | null
          external_popularity_signals?: Json | null
          finished_at?: string | null
          id?: number
          initiated_by_user_id?: string | null
          num_pages?: number | null
          paper_uuid?: string
          pdf_url?: string | null
          processing_time_seconds?: number | null
          signals?: Json | null
          started_at?: string | null
          status?: string
          summaries?: Json | null
          title?: string | null
          total_cost?: number | null
          updated_at?: string
        }
        Relationships: []
      }
      user_interactions: {
        Row: {
          created_at: string
          id: number
          interaction_type: string
          metadata: Json | null
          paper_uuid: string
          user_id: string
        }
        Insert: {
          created_at?: string
          id?: number
          interaction_type: string
          metadata?: Json | null
          paper_uuid: string
          user_id: string
        }
        Update: {
          created_at?: string
          id?: number
          interaction_type?: string
          metadata?: Json | null
          paper_uuid?: string
          user_id?: string
        }
        Relationships: []
      }
      user_lists: {
        Row: {
          created_at: string
          id: number
          paper_id: number
          user_id: string
        }
        Insert: {
          created_at: string
          id?: number
          paper_id: number
          user_id: string
        }
        Update: {
          created_at?: string
          id?: number
          paper_id?: number
          user_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "fk_user_lists_paper"
            columns: ["paper_id"]
            isOneToOne: false
            referencedRelation: "papers"
            referencedColumns: ["id"]
          },
        ]
      }
      user_preference_clusters: {
        Row: {
          cluster_index: number
          embedding: string
          id: number
          interaction_count: number
          updated_at: string
          user_id: string
          weight: number
        }
        Insert: {
          cluster_index: number
          embedding: string
          id?: number
          interaction_count?: number
          updated_at?: string
          user_id: string
          weight?: number
        }
        Update: {
          cluster_index?: number
          embedding?: string
          id?: number
          interaction_count?: number
          updated_at?: string
          user_id?: string
          weight?: number
        }
        Relationships: []
      }
      user_requests: {
        Row: {
          arxiv_id: string
          authors: string | null
          created_at: string
          id: number
          is_processed: boolean
          processed_slug: string | null
          title: string | null
          user_id: string
        }
        Insert: {
          arxiv_id: string
          authors?: string | null
          created_at: string
          id?: number
          is_processed: boolean
          processed_slug?: string | null
          title?: string | null
          user_id: string
        }
        Update: {
          arxiv_id?: string
          authors?: string | null
          created_at?: string
          id?: number
          is_processed?: boolean
          processed_slug?: string | null
          title?: string | null
          user_id?: string
        }
        Relationships: []
      }
    }
    Views: {
      [_ in never]: never
    }
    Functions: {
      match_papers_by_embedding: {
        Args: {
          exclude_uuids?: string[]
          match_count?: number
          query_embedding: string
        }
        Returns: {
          authors: string
          embedding: string
          external_popularity_signals: Json
          finished_at: string
          paper_uuid: string
          signals: Json
          similarity: number
          title: string
        }[]
      }
      set_paper_summary_if_null: {
        Args: { p_paper_uuid: string; p_summary: string }
        Returns: {
          was_set: boolean
        }[]
      }
    }
    Enums: {
      [_ in never]: never
    }
    CompositeTypes: {
      [_ in never]: never
    }
  }
}

type DatabaseWithoutInternals = Omit<Database, "__InternalSupabase">

type DefaultSchema = DatabaseWithoutInternals[Extract<keyof Database, "public">]

export type Tables<
  DefaultSchemaTableNameOrOptions extends
    | keyof (DefaultSchema["Tables"] & DefaultSchema["Views"])
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
        DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
      DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])[TableName] extends {
      Row: infer R
    }
    ? R
    : never
  : DefaultSchemaTableNameOrOptions extends keyof (DefaultSchema["Tables"] &
        DefaultSchema["Views"])
    ? (DefaultSchema["Tables"] &
        DefaultSchema["Views"])[DefaultSchemaTableNameOrOptions] extends {
        Row: infer R
      }
      ? R
      : never
    : never

export type TablesInsert<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Insert: infer I
    }
    ? I
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Insert: infer I
      }
      ? I
      : never
    : never

export type TablesUpdate<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Update: infer U
    }
    ? U
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Update: infer U
      }
      ? U
      : never
    : never

export type Enums<
  DefaultSchemaEnumNameOrOptions extends
    | keyof DefaultSchema["Enums"]
    | { schema: keyof DatabaseWithoutInternals },
  EnumName extends DefaultSchemaEnumNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"]
    : never = never,
> = DefaultSchemaEnumNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"][EnumName]
  : DefaultSchemaEnumNameOrOptions extends keyof DefaultSchema["Enums"]
    ? DefaultSchema["Enums"][DefaultSchemaEnumNameOrOptions]
    : never

export type CompositeTypes<
  PublicCompositeTypeNameOrOptions extends
    | keyof DefaultSchema["CompositeTypes"]
    | { schema: keyof DatabaseWithoutInternals },
  CompositeTypeName extends PublicCompositeTypeNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"]
    : never = never,
> = PublicCompositeTypeNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"][CompositeTypeName]
  : PublicCompositeTypeNameOrOptions extends keyof DefaultSchema["CompositeTypes"]
    ? DefaultSchema["CompositeTypes"][PublicCompositeTypeNameOrOptions]
    : never

export const Constants = {
  public: {
    Enums: {},
  },
} as const
