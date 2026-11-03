/** Friendlier words for the values the lead model was trained on (the values themselves are sent unchanged). */
export const OCCUPATION_LABEL: Record<string, string> = {
  "Working Professional": "Working",
  Student: "Student",
  Unemployed: "Looking for work",
  Businessman: "Running a business",
  Housewife: "Homemaker",
  Other: "Something else",
};

export interface ProfileOptions {
  occupations: string[];
  specializations: string[];
  age_brackets: string[];
  how_heard: string[];
}
