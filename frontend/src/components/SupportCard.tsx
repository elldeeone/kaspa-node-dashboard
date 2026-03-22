import { HeartIcon } from "./icons";

export function SupportCard() {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/70 p-4 sm:p-6">
      <div className="mb-4 flex items-center gap-2">
        <HeartIcon className="h-5 w-5 text-teal-400" />
        <h2 className="text-lg font-semibold text-gray-50">Support the Network</h2>
      </div>
      <p className="mb-4 text-sm text-zinc-400">
        The very heart of Kaspa is the public nodes. Please consider making your node public.
      </p>
      <div className="rounded-lg border border-zinc-700 bg-zinc-800/50 p-4">
        <p className="text-sm text-zinc-300">
          <span className="font-medium text-teal-400">To support the network:</span> Forward TCP port{" "}
          <span className="rounded bg-zinc-700 px-2 py-1 font-mono text-teal-400">16111</span> on your firewall to your Umbrel node IP address.
        </p>
      </div>
    </div>
  );
}
