from django.db import models

# Create your models here.
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.urls import reverse

class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("Email is required")
        email = self.normalize_email(email)
        if not email.endswith("@ubu.ac.th"):
            raise ValueError("Email must be a university email (@ubu.ac.th)")
        user = self.model(email=email, **extra_fields)
        user.set_password(password)           # hash password
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self._create_user(email, password, **extra_fields)

# ---------- User ----------
class User(AbstractUser):
    # ตัด username ออก ใช้ email แทน
    username = None
    email = models.EmailField(unique=True)

    class Roles(models.TextChoices):
        STUDENT = "STUDENT", "Student"
        TEACHER = "TEACHER", "Teacher"
        ADMIN   = "ADMIN", "Admin"


    base_role = Roles.ADMIN
    role = models.CharField(max_length=20, choices=Roles.choices, default=base_role)
    personal_id = models.CharField(max_length=20, blank=True, null=True, unique=False)
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []  # createsuperuser จะถามแค่อีเมล/พาสเวิร์ด

    objects = UserManager()

    groups = models.ManyToManyField(
        "auth.Group",
        verbose_name="groups",
        blank=True,
        help_text="The groups this user belongs to. A user will get all permissions granted to each of their groups.",
        related_name="users_user_groups",
    )
    user_permissions = models.ManyToManyField(
        "auth.Permission",
        verbose_name="user permissions",
        blank=True,
        help_text="Specific permissions for this user.",
        related_name="users_user_permissions",
    )
    
    @property
    def get_dashboard_url(self):
        if self.role == self.Roles.TEACHER:
            return reverse('teacher:dashboard')
        elif self.role == self.Roles.STUDENT:
            # สมมติว่า URL dashboard ของนักเรียนชื่อ 'student:dashboard'
            return reverse('student:dashboard')
        # ค่า Default สำหรับ Admin หรือ Role อื่นๆ
        return '/'

    def __str__(self):
        return f"{self.email} ({self.get_role_display()})"


class Students(models.Model):
    base_role = User.Roles.STUDENT
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="student_profile")
    name = models.CharField(max_length=100)
    profile_image = models.ImageField(
        upload_to='profiles/student_images/', # ตำแหน่งที่จะเก็บรูป
        null=True,                          # อนุญาตให้เป็น NULL ใน DB
        blank=True                          # อนุญาตให้เว้นว่างในฟอร์ม
    )

    def __str__(self):
        return f"{self.user.email} - {self.user.personal_id or 'no-id'}"


class Teachers(models.Model):
    base_role = User.Roles.TEACHER
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="teacher_profile")
    name = models.CharField(max_length=100)
    profile_image = models.ImageField(
        upload_to='profiles/teacher_images/', # แยกโฟลเดอร์เพื่อความเป็นระเบียบ
        null=True,
        blank=True
    )

    def __str__(self):
        return f"{self.user.email} - {self.user.personal_id or 'no-id'}"