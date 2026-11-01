package com.financetracker.access.domain;

import java.time.Instant;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

/** Port of django.contrib.auth.models.User (the fields this app uses). */
@Entity
@Table(name = "access_users")
public class UserAccount {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 150)
    private String username;

    @Column(nullable = false, length = 254)
    private String email = "";

    @Column(nullable = false, length = 150)
    private String firstName = "";

    @Column(nullable = false, length = 150)
    private String lastName = "";

    /** Django hash string, e.g. pbkdf2_sha256$1000000$salt$hash; "" or "!..." means no usable password. */
    @Column(nullable = false, length = 128)
    private String password = "";

    @Column(nullable = false)
    private boolean staff;

    @Column(nullable = false)
    private boolean superuser;

    @Column(nullable = false)
    private boolean active = true;

    private Instant lastLogin;

    @Column(nullable = false)
    private Instant dateJoined = Instant.now();

    public String userId() {
        return String.valueOf(id);
    }

    /** Django has_usable_password(). */
    public boolean hasUsablePassword() {
        return password == null || !password.startsWith("!");
    }

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public String getUsername() { return username; }
    public void setUsername(String username) { this.username = username; }
    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email == null ? "" : email; }
    public String getFirstName() { return firstName; }
    public void setFirstName(String firstName) { this.firstName = firstName == null ? "" : firstName; }
    public String getLastName() { return lastName; }
    public void setLastName(String lastName) { this.lastName = lastName == null ? "" : lastName; }
    public String getPassword() { return password; }
    public void setPassword(String password) { this.password = password == null ? "" : password; }
    public boolean isStaff() { return staff; }
    public void setStaff(boolean staff) { this.staff = staff; }
    public boolean isSuperuser() { return superuser; }
    public void setSuperuser(boolean superuser) { this.superuser = superuser; }
    public boolean isActive() { return active; }
    public void setActive(boolean active) { this.active = active; }
    public Instant getLastLogin() { return lastLogin; }
    public void setLastLogin(Instant lastLogin) { this.lastLogin = lastLogin; }
    public Instant getDateJoined() { return dateJoined; }
    public void setDateJoined(Instant dateJoined) { this.dateJoined = dateJoined; }
}
