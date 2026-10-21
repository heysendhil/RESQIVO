import ValidatePlan from "./validate-plan";

export default function Home() {
  return (
    <div className="flex flex-1 justify-center bg-zinc-50 font-sans dark:bg-black">
      <main className="flex w-full max-w-4xl flex-col gap-8 bg-white px-4 py-12 sm:px-10 dark:bg-black">
        <header className="flex flex-col gap-2">
          <h1 className="text-3xl font-semibold tracking-tight">RESQIVO</h1>
          <p className="text-zinc-600 dark:text-zinc-400">
            Every Second. Every Life.
          </p>
          <p className="w-fit rounded-md bg-amber-100 px-2 py-1 text-xs font-medium text-amber-900 dark:bg-amber-950 dark:text-amber-200">
            Simulated scenario: synthetic data for planning and education only
          </p>
        </header>
        <ValidatePlan />
      </main>
    </div>
  );
}
