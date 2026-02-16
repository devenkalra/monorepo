// tailwind.config.js
module.exports = {
    content: [
        "./index.html",
        "./src/**/*.{js,jsx,ts,tsx}"
    ],
    darkMode: "class", // enable class-based dark mode
    theme: {
        extend: {
            colors: {
                primary: "hsl(210, 70%, 50%)",
                accent: "hsl(45, 90%, 55%)"
            }
        }
    },
    plugins: []
};
