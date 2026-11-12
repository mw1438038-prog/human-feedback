
/* HUMAN FEEDBACK - Homepage Visual Interactions */

document.addEventListener("DOMContentLoaded", function () {

    const menuToggle = document.getElementById("menuToggle");
    const navLinks = document.getElementById("navLinks");

    if (menuToggle && navLinks) {

        menuToggle.addEventListener("click", function () {
            navLinks.classList.toggle("show");

            menuToggle.textContent =
                navLinks.classList.contains("show") ? "✕" : "☰";
        });

        navLinks.querySelectorAll("a").forEach(function (link) {

            link.addEventListener("click", function () {
                navLinks.classList.remove("show");
                menuToggle.textContent = "☰";
            });

        });

    }

});
