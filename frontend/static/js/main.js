// Main JavaScript for Smart Classroom Monitor
document.addEventListener('DOMContentLoaded', function() {
    // Highlight active link in sidebar is handled by Jinja template class assignment
    
    // Smooth scrolling
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function (e) {
            e.preventDefault();
            document.querySelector(this.getAttribute('href')).scrollIntoView({
                behavior: 'smooth'
            });
        });
    });
});
