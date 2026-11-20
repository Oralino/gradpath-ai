import { ProfileForm } from "@/components/ProfileForm";

// Profile screen (DESIGN.md, Screens 4). A server component: only the heading renders here; the
// form and the browser-only storage live in the client <ProfileForm />.
export default function ProfilePage() {
  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-4">
      <h1 className="text-display">Your profile</h1>
      <ProfileForm />
    </div>
  );
}
