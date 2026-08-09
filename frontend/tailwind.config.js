/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#102a43",
        sea: "#243b53",
        foam: "#f0f4f8",
        accent: "#2bb0ed",
        ember: "#f0b429",
      },
      fontFamily: {
        display: ['"Fraunces"', "Georgia", "serif"],
        body: ['"Source Sans 3"', "Segoe UI", "sans-serif"],
      },
    },
  },
  plugins: [],
};
