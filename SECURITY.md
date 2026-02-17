# Security Policy

## Supported Versions

| Version       | Supported          |
|---------------|--------------------|
| Next-1.1.x    | :white_check_mark: |
| < 1.1.0       | :x:                |

## Reporting a Vulnerability

If you discover a security vulnerability in this project, please report it responsibly.

**Do NOT open a public GitHub issue for security vulnerabilities.**

### How to Report

1. **Email**: Send a detailed report to the project maintainer via GitHub private message or email
2. **Include**:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

### What to Expect

- Acknowledgment within **48 hours**
- Status update within **7 days**
- Fix released as soon as practical, depending on severity

### Scope

The following are considered in scope:

- Authentication bypass in WebUI
- SQL injection in database queries
- Cross-site scripting (XSS) in WebUI
- Unauthorized access to API endpoints
- Data exposure through improper access controls
- LLM prompt injection that bypasses safety controls

### Out of Scope

- Vulnerabilities in third-party dependencies (report to upstream)
- Issues requiring physical access to the server
- Social engineering attacks
- Denial of service through expected functionality

## Security Best Practices

When deploying this plugin:

1. **Change the default WebUI password** immediately after installation
2. **Do not expose the WebUI port** (default: 7833) to the public internet
3. **Use a reverse proxy** with HTTPS if remote access is needed
4. **Keep dependencies updated** by running `pip install -r requirements.txt --upgrade` regularly
5. **Back up your data** regularly, including persona files and the database
