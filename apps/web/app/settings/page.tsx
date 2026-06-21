import { KeyVault } from "@/components/settings/KeyVault";

export default function SettingsPage() {
  return (
    <div className="flex flex-col gap-7">
      <header>
        <h1 className="page-title">API Keys</h1>
        <p className="page-sub">Saved encrypted on the server. Paste once — the browser never holds your key after saving.</p>
      </header>
      <KeyVault />
    </div>
  );
}
