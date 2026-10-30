/** Complete synthetic records keep tests aligned with the contracts used by the app */
import type {
  Assessment,
  Announcement,
  Course,
  CourseInfo,
  Plan,
  Readiness,
} from "../src/study/model.ts";
import type { Clip } from "../src/timey/model.ts";

export const course = (value: Partial<Course> = {}): Course => ({
  id: "course",
  code: "CSSE1001",
  name: "Programming",
  profile: "",
  prerequisites: "",
  notes: "",
  verified: false,
  ...value,
});
export const assessment = (value: Partial<Assessment> = {}): Assessment => ({
  id: "assessment",
  course: "course",
  title: "Assignment",
  weight: 20,
  ...value,
});
export const announcement = (value: Partial<Announcement> = {}): Announcement => ({
  id: "announcement",
  title: "Meetup",
  notes: "",
  ...value,
});
export const plan = (value: Partial<Plan> = {}): Plan => ({
  revision: 0,
  courses: [],
  assessments: [],
  announcements: [],
  settings: { buffer: 2, target: 75 },
  ...value,
});
export const readiness = (value: Partial<Readiness> = {}): Readiness => ({
  status: "review",
  missing: [],
  incompatible: [],
  wording: "",
  skills: [],
  required: [],
  ...value,
});
export const info = (value: Partial<CourseInfo> = {}): CourseInfo => ({
  details: {},
  readiness: readiness(),
  url: "https://programs-courses.uq.edu.au/course.html?course_code=CSSE1001",
  reviews: [],
  secat: [],
  offerings: [],
  ...value,
});
export const json = (value: unknown, status = 200, headers: HeadersInit = {}): Response =>
  new Response(JSON.stringify(value), { status, headers });
export const clip = (value: Partial<Clip> = {}): Clip => ({
  source: "video",
  start: 0,
  url: "/download/cached",
  kind: "video",
  width: 960,
  height: 540,
  duration: 300,
  complete: true,
  ...value,
});
