// Google Analytics (gtag.js) configuration — shared by all pages.
// Each HTML page loads the gtag.js library asynchronously, then includes this file:
//   <script async src="https://www.googletagmanager.com/gtag/js?id=G-X0YCL6L7J2"></script>
//   <script src="js/gtag.js"></script>
window.GA_TRACKING_ID = "G-X0YCL6L7J2";

window.dataLayer = window.dataLayer || [];
function gtag() { dataLayer.push(arguments); }
gtag("js", new Date());
gtag("config", window.GA_TRACKING_ID);
