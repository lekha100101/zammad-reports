// sidebar.js

// Function to toggle sidebar visibility
function toggleSidebar() {
    const sidebar = document.querySelector('.sidebar');
    sidebar.classList.toggle('active');
}

// Function to close sidebar when clicking outside or on a link
function closeSidebar(event) {
    const sidebar = document.querySelector('.sidebar');
    const menuButton = document.querySelector('.menu-button');
    const links = document.querySelectorAll('.sidebar a');

    if (!sidebar.contains(event.target) && !menuButton.contains(event.target)) {
        sidebar.classList.remove('active');
    }
    links.forEach(link => {
        link.addEventListener('click', () => {
            sidebar.classList.remove('active');
        });
    });
}

// Function to set active state for current page navigation
function setActiveLink() {
    const links = document.querySelectorAll('.sidebar a');
    const currentPath = window.location.pathname;

    links.forEach(link => {
        if (link.getAttribute('href') === currentPath) {
            link.classList.add('active');
        } else {
            link.classList.remove('active');
        }
    });
}

// Smooth transition for opening and closing sidebar
const sidebar = document.querySelector('.sidebar');
const menuButton = document.querySelector('.menu-button');

menuButton.addEventListener('click', toggleSidebar);
window.addEventListener('click', closeSidebar);
window.addEventListener('load', setActiveLink);
