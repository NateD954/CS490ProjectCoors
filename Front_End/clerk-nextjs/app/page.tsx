import Link from "next/link";

export default function Landing() {
    return (
        <main className="flex min-h-screen flex-col items-center justify-center gap-6 p-8 text-center">
            <h1 className="text-4xl font-bold">Welcome to Review Lense</h1>
            <p className="max-w-xl text-lg text-gray-500">
                An app to ingest and summarize google reviews.
            </p>
            <Link
                href="/home"
                className="rounded-full bg-white px-6 py-3 font-medium text-black hover:bg-gray-200"
            >
                Get Started
            </Link>
        </main>
    );
}