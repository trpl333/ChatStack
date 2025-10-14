# Deploy Customer Site to neurospherevoice.com

## 🎯 Overview
Deploy the customer purchase and onboarding site to DigitalOcean and configure neurospherevoice.com domain.

---

## 📦 Step 1: Push Code to GitHub

From Replit, push the latest code:

```bash
git add static/pricing.html static/onboarding.html static/dashboard.html
git add customer_models.py init_customer_db.py main.py
git add deploy_customer_site.sh configure_nginx_neurosphere.sh
git commit -m "Add customer purchase and onboarding system"
git push origin main
```

---

## 🚀 Step 2: Deploy to DigitalOcean

SSH into your DigitalOcean server:

```bash
ssh root@209.38.143.71
cd /opt/ChatStack

# Pull latest code
git pull origin main

# Run deployment script
chmod +x deploy_customer_site.sh
./deploy_customer_site.sh

# Configure Nginx
chmod +x configure_nginx_neurosphere.sh
sudo ./configure_nginx_neurosphere.sh
```

---

## 🌐 Step 3: Update DNS on Bluehost

1. **Log into Bluehost** (bluehost.com)
2. **Go to Domains** → Select **neurospherevoice.com** → **DNS**
3. **Update A Records:**

   | Type | Name | Points to | TTL |
   |------|------|-----------|-----|
   | A    | @    | 209.38.143.71 | 14400 |
   | A    | www  | 209.38.143.71 | 14400 |

4. **Save changes**
5. **Wait 5-30 minutes** for DNS propagation

**Check propagation:**
```bash
# From your local machine
dig neurospherevoice.com
nslookup neurospherevoice.com
```

---

## 🔒 Step 4: Install SSL Certificate (HTTPS)

Once DNS is propagated, run on DigitalOcean:

```bash
sudo certbot --nginx -d neurospherevoice.com -d www.neurospherevoice.com
```

Follow prompts:
- Enter email for renewal notifications
- Agree to Terms of Service
- Choose: **Redirect HTTP to HTTPS** (option 2)

---

## 🗄️ Step 5: Initialize Customer Database

```bash
cd /opt/ChatStack
python init_customer_db.py
```

This creates:
- `customers` table
- `customer_configurations` table  
- `customer_usage` table

---

## ✅ Step 6: Test the Site

Visit:
- **http://neurospherevoice.com** → Redirects to pricing
- **http://neurospherevoice.com/pricing.html** → Pricing page
- **http://neurospherevoice.com/onboarding.html** → Onboarding wizard
- **http://neurospherevoice.com/dashboard.html** → Customer dashboard

API endpoints:
- `POST /api/customers/onboard`
- `GET /api/customers/<id>`
- `PUT /api/customers/<id>/settings`

---

## 🔧 Troubleshooting

### DNS not propagating?
```bash
# Check DNS status
dig neurospherevoice.com @8.8.8.8
```

### Nginx errors?
```bash
# Check logs
sudo tail -f /var/log/nginx/error.log

# Test config
sudo nginx -t

# Reload
sudo systemctl reload nginx
```

### Flask API not working?
```bash
# Check Flask app is running
curl http://localhost:5000/admin-status

# Restart Flask
cd /opt/ChatStack
docker-compose restart web
```

### SSL certificate issues?
```bash
# Check certbot
sudo certbot certificates

# Renew manually
sudo certbot renew --dry-run
```

---

## 📁 File Structure

```
/opt/ChatStack/               # Flask backend
├── main.py                   # Backend with API routes
├── customer_models.py        # Database models
└── static/
    ├── admin.html           # Existing admin panel
    └── ...

/var/www/neurospherevoice/   # Customer site (static files)
├── index.html               # Redirect to pricing
├── pricing.html            # Pricing page
├── onboarding.html         # Onboarding wizard
└── dashboard.html          # Customer dashboard
```

---

## 🎯 Architecture

```
neurospherevoice.com (Port 80/443)
         ↓
    Nginx Reverse Proxy
         ↓
    ┌────────────────┐
    │ Static Files   │ → /var/www/neurospherevoice/
    │ (HTML/CSS/JS)  │
    └────────────────┘
         
    ┌────────────────┐
    │ API Requests   │ → http://localhost:5000/api/
    │ (/api/*)       │    (Flask Backend)
    └────────────────┘
```

---

## 🚨 Important Notes

1. **Customer DB is on same PostgreSQL** as phone system
2. **Flask backend serves both** admin panel and customer APIs
3. **Static files separate** for performance
4. **API authentication needed** before production (noted by architect)

---

## 📝 Post-Deployment Checklist

- [ ] Code pushed to GitHub
- [ ] Files deployed to /var/www/neurospherevoice/
- [ ] Nginx configured and reloaded
- [ ] DNS updated on Bluehost
- [ ] DNS propagated (test with dig)
- [ ] SSL certificate installed
- [ ] Customer database initialized
- [ ] Test pricing page loads
- [ ] Test onboarding flow
- [ ] Test API endpoints
- [ ] Monitor logs for errors

---

## 🎉 Success!

Your customer site is now live at:
- **https://neurospherevoice.com**

Customers can:
1. View pricing packages
2. Complete onboarding
3. Access their dashboard
4. Configure their AI agent
