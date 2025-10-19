"use client";

import { useState } from "react";

export default function Home() {
  const [video, setVideo] = useState<File | null>(null);
  const [image, setImage] = useState<File | null>(null);
  const [text, setText] = useState("");
  const [response, setResponse] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!video || !image || !text) {
      alert("Please upload both files and enter text");
      return;
    }

    const formData = new FormData();
    formData.append("video", video);
    formData.append("image", image);
    formData.append("text", text);

    setLoading(true);
    try {
      const res = await fetch("http://localhost:8001/process_ai/", {
        method: "POST",
        body: formData,
      });      
      const data = await res.json();
      setResponse(data);
    } catch (error) {
      console.error(error);
      alert("Something went wrong. Check your backend connection.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-6 bg-gray-100">
      <div className="bg-white shadow-md rounded-xl p-8 w-full max-w-md">
        <h1 className="text-2xl font-bold mb-4 text-center">
          AI Video Pipeline
        </h1>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <input
            type="file"
            accept="video/*"
            onChange={(e) => setVideo(e.target.files?.[0] || null)}
            className="border p-2 rounded"
          />
          <input
            type="file"
            accept="image/*"
            onChange={(e) => setImage(e.target.files?.[0] || null)}
            className="border p-2 rounded"
          />
          <textarea
            placeholder="Describe how you want to modify the video..."
            value={text}
            onChange={(e) => setText(e.target.value)}
            className="border p-2 rounded"
          />

          <button
            type="submit"
            disabled={loading}
            className="bg-blue-600 text-white py-2 rounded hover:bg-blue-700"
          >
            {loading ? "Processing..." : "Upload & Process"}
          </button>
        </form>

        {response && (
          <div className="mt-6 text-sm">
            <p className="font-semibold">Backend Response:</p>
            <pre className="bg-gray-100 p-2 rounded overflow-x-auto">
              {JSON.stringify(response, null, 2)}
            </pre>

            {response.video_url && (
              <div className="mt-4">
                <p className="font-semibold mb-1">Uploaded Video:</p>
                <video
                  src={response.video_url}
                  controls
                  className="rounded-lg w-full"
                />
              </div>
            )}

            {response.image_url && (
              <div className="mt-4">
                <p className="font-semibold mb-1">Uploaded Image:</p>
                <img
                  src={response.image_url}
                  alt="Uploaded"
                  className="rounded-lg w-full"
                />
              </div>
            )}
          </div>
        )}
      </div>
    </main>
  );
}
